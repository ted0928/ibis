# Copyright 2014 Cloudera Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import annotations

import pytest

import ibis
import ibis.backends.sql.compilers as sc
import ibis.expr.operations as ops
import ibis.expr.types as ir
from ibis import _
from ibis.tests.util import assert_equal


@pytest.fixture
def sql_table():
    return ibis.table(
        [
            ("v1", "decimal(12, 2)"),
            ("v2", "decimal(10, 4)"),
            ("v3", "int32"),
            ("v4", "int64"),
            ("v5", "float32"),
            ("v6", "double"),
            ("v7", "string"),
            ("v8", "boolean"),
        ],
        "testing",
    )


@pytest.fixture(params=(ibis.coalesce, ibis.greatest, ibis.least))
def function(request):
    return request.param


@pytest.mark.parametrize(
    "colname",
    [
        "tinyint_col",
        "smallint_col",
        "int_col",
        "bigint_col",
        "float_col",
        "double_col",
    ],
)
def test_abs(functional_alltypes, lineitem, colname):
    fname = "abs"
    op = ops.Abs

    expr = functional_alltypes[colname]
    _check_unary_op(expr, fname, op, type(expr))

    expr = lineitem.l_extendedprice
    _check_unary_op(expr, fname, op, type(expr))


def test_group_concat(functional_alltypes):
    col = functional_alltypes.string_col

    expr = col.group_concat()
    assert isinstance(expr.op(), ops.GroupConcat)
    op = expr.op()
    assert op.sep == ibis.literal(",").op()
    assert op.where is None

    expr = col.group_concat("|")
    op = expr.op()
    assert op.sep == ibis.literal("|").op()
    assert op.where is None


def test_zero_ifnull(functional_alltypes):
    dresult = functional_alltypes.double_col.fill_null(0)

    iresult = functional_alltypes.int_col.fill_null(0)

    assert type(dresult.op()) is ops.Coalesce
    assert type(dresult) is ir.FloatingColumn

    # Impala upconverts all ints to bigint. Hmm.
    assert type(iresult) is type(iresult)


def test_fill_null(functional_alltypes):
    result = functional_alltypes.double_col.fill_null(5)
    assert isinstance(result, ir.FloatingColumn)

    assert isinstance(result.op(), ops.Coalesce)

    result = functional_alltypes.bool_col.fill_null(True)
    assert isinstance(result, ir.BooleanColumn)

    # Highest precedence type
    result = functional_alltypes.int_col.fill_null(functional_alltypes.bigint_col)
    assert isinstance(result, ir.IntegerColumn)


def test_ceil_floor(functional_alltypes, lineitem):
    cresult = functional_alltypes.double_col.ceil()
    fresult = functional_alltypes.double_col.floor()
    assert isinstance(cresult, ir.IntegerColumn)
    assert isinstance(fresult, ir.IntegerColumn)
    assert type(cresult.op()) is ops.Ceil
    assert type(fresult.op()) is ops.Floor

    cresult = ibis.literal(1.2345).ceil()
    fresult = ibis.literal(1.2345).floor()
    assert isinstance(cresult, ir.IntegerScalar)
    assert isinstance(fresult, ir.IntegerScalar)

    dec_col = lineitem.l_extendedprice
    cresult = dec_col.ceil()
    fresult = dec_col.floor()
    assert isinstance(cresult, ir.DecimalColumn)
    assert cresult.type() == dec_col.type()

    assert isinstance(fresult, ir.DecimalColumn)
    assert fresult.type() == dec_col.type()


def test_sign(functional_alltypes, lineitem):
    result = functional_alltypes.double_col.sign()
    assert isinstance(result, ir.FloatingColumn)
    assert type(result.op()) is ops.Sign

    result = ibis.literal(1.2345).sign()
    assert isinstance(result, ir.FloatingScalar)

    dec_col = lineitem.l_extendedprice
    result = dec_col.sign()
    assert isinstance(result, ir.DecimalColumn)


def test_round(functional_alltypes, lineitem):
    result = functional_alltypes.double_col.round()
    assert isinstance(result, ir.IntegerColumn)
    assert result.op().args[1] == ibis.literal(0).op()

    result = functional_alltypes.double_col.round(2)
    assert isinstance(result, ir.FloatingColumn)
    assert result.op().args[1] == ibis.literal(2).op()

    # Even integers are double (at least in Impala, check with other DB
    # implementations)
    result = functional_alltypes.int_col.round(2)
    assert isinstance(result, ir.FloatingColumn)

    dec = lineitem.l_extendedprice
    result = dec.round()
    assert isinstance(result, ir.DecimalColumn)

    result = dec.round(2)
    assert isinstance(result, ir.DecimalColumn)

    result = ibis.literal(1.2345).round()
    assert isinstance(result, ir.IntegerScalar)


def _check_unary_op(expr, fname, ex_op, ex_type):
    result = getattr(expr, fname)()
    assert type(result.op()) is ex_op
    assert type(result) is ex_type


def test_coalesce_instance_method(sql_table):
    v7 = sql_table.v7
    v5 = sql_table.v5.cast("string")
    v8 = sql_table.v8.cast("string")

    result = v7.coalesce(v5, v8, "foo")
    expected = ibis.coalesce(v7, v5, v8, "foo")
    assert_equal(result, expected)


def test_integer_promotions(sql_table, function):
    t = sql_table

    expr = function(t.v3, t.v4)
    assert isinstance(expr, ir.IntegerColumn)

    expr = function(5, t.v3)
    assert isinstance(expr, ir.IntegerColumn)

    expr = function(5, 12)
    assert isinstance(expr, ir.IntegerScalar)


def test_floats(sql_table, function):
    t = sql_table

    expr = function(t.v5)
    assert isinstance(expr, ir.FloatingColumn)

    expr = function(5.5, t.v5)
    assert isinstance(expr, ir.FloatingColumn)

    expr = function(5.5, 5)
    assert isinstance(expr, ir.FloatingScalar)


def test_deferred(sql_table, function):
    expr = function(None, _.v3, 2)
    res = expr.resolve(sql_table)
    sol = function(None, sql_table.v3, 2)
    assert res.equals(sol)


def test_no_arguments_errors(function):
    with pytest.raises(
        TypeError,
        match=rf"{function.__name__}\(\) missing 1 required positional argument",
    ):
        function()


@pytest.mark.parametrize(
    "name", [name.lower().removesuffix("compiler") for name in sc.__all__]
)
def test_compile_without_dependencies(name):
    table = ibis.table({"a": "int64"}, name="t")
    assert isinstance(ibis.to_sql(table, dialect=name), str)
