import unittest
import tempfile
import datetime
import os.path
import shutil

import numpy
import pyarrow
import datafusion

# used to write parquet files
import pyarrow.parquet

from .generic import *


class TestCase(unittest.TestCase):

    def setUp(self):
        # Create a temporary directory
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        # Remove the directory after the test
        shutil.rmtree(self.test_dir)

    def test_no_table(self):
        with self.assertRaises(Exception):
            datafusion.Context().sql("SELECT a FROM b").collect()

    def test_register(self):
        ctx = datafusion.ExecutionContext()

        path = write_parquet(os.path.join(self.test_dir, 'a.parquet'), data())

        ctx.register_parquet("t", path)

        self.assertEqual(ctx.tables(), {"t"})

    def test_execute(self):
        ctx = datafusion.ExecutionContext()

        # single column, "a"
        path = write_parquet(os.path.join(self.test_dir, 'a.parquet'), data())
        ctx.register_parquet("t", path)

        self.assertEqual(ctx.tables(), {"t"})

        # count
        expected = pyarrow.array([100], pyarrow.uint64())
        expected = [pyarrow.RecordBatch.from_arrays([expected], ['COUNT(a)'])]
        self.assertEqual(expected, ctx.sql("SELECT COUNT(a) FROM t").collect())

        # where
        expected = pyarrow.array([50], pyarrow.uint64())
        expected = [pyarrow.RecordBatch.from_arrays([expected], ['COUNT(a)'])]
        self.assertEqual(expected, ctx.sql("SELECT COUNT(a) FROM t WHERE a > 10").collect())

        # group by
        result = ctx.sql("SELECT CAST(a as int), COUNT(a) FROM t GROUP BY CAST(a as int)").collect()

        expected_cast = pyarrow.array([50,  0, 49], pyarrow.int32())
        expected_count = pyarrow.array([31, 50, 19], pyarrow.uint64())
        expected = [pyarrow.RecordBatch.from_arrays([expected_cast, expected_count], ['CAST(a as Int32)', 'COUNT(a)'])]
        numpy.testing.assert_equal(expected, result)

        # order by
        result = ctx.sql("SELECT a, CAST(a AS int) FROM t ORDER BY a DESC LIMIT 2").collect()
        expected_a = pyarrow.array([50.0219, 50.0152], pyarrow.float64())
        expected_cast = pyarrow.array([50, 50], pyarrow.int32())
        expected = [pyarrow.RecordBatch.from_arrays([expected_a, expected_cast], ['a', 'CAST(a as Int32)'])]
        numpy.testing.assert_equal(expected[0].column(1), expected[0].column(1))

    def test_cast(self):
        """
        Verify that we can cast
        """
        ctx = datafusion.ExecutionContext()

        path = write_parquet(os.path.join(self.test_dir, 'a.parquet'), data())
        ctx.register_parquet("t", path)

        valid_types = [
            'smallint',
            'int',
            'bigint',
            'float(32)',
            'float(64)',
            'float',
        ]

        select = ', '.join([f'CAST(9 AS {t}) AS A{i}' for i, t in enumerate(valid_types)])

        # can execute, which implies that we can cast
        ctx.sql(f'SELECT {select} FROM t').collect()

    def _test_udf(self, udf, args, return_type, array, expected):
        ctx = datafusion.ExecutionContext()

        # write to disk
        path = write_parquet(os.path.join(self.test_dir, 'a.parquet'), array)
        ctx.register_parquet("t", path)

        ctx.register_udf("udf", udf, args, return_type)

        batches = ctx.sql("SELECT udf(a) AS tt FROM t").collect()

        result = batches[0].column(0)

        self.assertEqual(expected, result)

    def test_udf_identity(self):
        self._test_udf(
            lambda x: x,
            [pyarrow.float64()],
            pyarrow.float64(),
            pyarrow.array([-1.2, None, 1.2]),
            pyarrow.array([-1.2, None, 1.2])
        )

    def test_udf(self):
        self._test_udf(
            lambda x: x.is_null(),
            [pyarrow.float64()],
            pyarrow.bool_(),
            pyarrow.array([-1.2, None, 1.2]),
            pyarrow.array([False, True, False])
        )


class TestIO(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        # Remove the directory after the test
        shutil.rmtree(self.test_dir)

    def _test_data(self, data):
        ctx = datafusion.ExecutionContext()

        # write to disk
        path = write_parquet(os.path.join(self.test_dir, 'a.parquet'), data)
        ctx.register_parquet("t", path)

        batches = ctx.sql("SELECT a AS tt FROM t").collect()

        result = batches[0].column(0)

        numpy.testing.assert_equal(data, result)

    def test_nans(self):
        self._test_data(data_with_nans())

    def test_utf8(self):
        array = pyarrow.array(["a", "b", "c"], pyarrow.utf8(), numpy.array([False, True, False]))
        self._test_data(array)

    # Not writtable to parquet
    @unittest.expectedFailure
    def test_large_utf8(self):
        array = pyarrow.array(["a", "b", "c"], pyarrow.large_utf8(), numpy.array([False, True, False]))
        self._test_data(array)

    # Error from Arrow
    @unittest.expectedFailure
    def test_datetime_s(self):
        self._test_data(data_datetime('s'))

    # C data interface missing
    @unittest.expectedFailure
    def test_datetime_ms(self):
        self._test_data(data_datetime('ms'))

    # C data interface missing
    @unittest.expectedFailure
    def test_datetime_us(self):
        self._test_data(data_datetime('us'))

    # Not writtable to parquet
    @unittest.expectedFailure
    def test_datetime_ns(self):
        self._test_data(data_datetime('ns'))

    # Not writtable to parquet
    @unittest.expectedFailure
    def test_timedelta_s(self):
        self._test_data(data_timedelta('s'))

    # Not writtable to parquet
    @unittest.expectedFailure
    def test_timedelta_ms(self):
        self._test_data(data_timedelta('ms'))

    # Not writtable to parquet
    @unittest.expectedFailure
    def test_timedelta_us(self):
        self._test_data(data_timedelta('us'))

    # Not writtable to parquet
    @unittest.expectedFailure
    def test_timedelta_ns(self):
        self._test_data(data_timedelta('ns'))

    # C data interface missing
    @unittest.expectedFailure
    def test_date32(self):
        array = pyarrow.array([
            datetime.date(2000, 1, 1),
            datetime.date(1980, 1, 1),
            datetime.date(2030, 1, 1),
        ], pyarrow.date32(), numpy.array([False, True, False]))
        self._test_data(array)

    def test_binary_variable(self):
        array = pyarrow.array([b'1', b'2', b'3'], pyarrow.binary(), numpy.array([False, True, False]))
        self._test_data(array)

    # C data interface missing
    @unittest.expectedFailure
    def test_binary_fixed(self):
        array = pyarrow.array([b'1111', b'2222', b'3333'], pyarrow.binary(4), numpy.array([False, True, False]))
        self._test_data(array)

    # Not writtable to parquet
    @unittest.expectedFailure
    def test_large_binary(self):
        array = pyarrow.array([b'1111', b'2222', b'3333'], pyarrow.large_binary(), numpy.array([False, True, False]))
        self._test_data(array)

    def test_binary_other(self):
        self._test_data(data_binary_other())

    def test_bool(self):
        array = pyarrow.array([False, True, True], None, numpy.array([False, True, False]))
        self._test_data(array)

    def test_u32(self):
        array = pyarrow.array([0, 1, 2], None, numpy.array([False, True, False]))
        self._test_data(array)
