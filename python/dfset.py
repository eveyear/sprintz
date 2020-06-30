#!/usr/bin/env python

import abc
import os
import tempfile

import numpy as np
import pandas as pd


class BaseDfSet(abc.ABC):

    def __init__(self, dfsdir, filetype='csv',
                 read_kwargs=None, write_kwargs=None):
        self._dfsdir = dfsdir
        assert filetype in ('csv', 'npy', 'parquet', 'h5')
        self._filetype = filetype
        self.read_kwargs = read_kwargs or {}
        self.write_kwargs = write_kwargs or {}
        self._endswith = '.' + filetype
        self._ids = None

    def _rm_endswith(self, fname):
        if self._endswith and fname.endswith(self._endswith):
            fname = fname[:-len(self._endswith)]
        return fname

    def _id_from_dirname(self, fname):
        # print(f"id = {self._rm_endswith(fname)} from dirname {fname}")
        return self._rm_endswith(fname)

    def _path(self, dfid, col=None):
        if col is None:
            os.path.join(self._dfsdir, dfid)
        fname = col + self._endswith if col is not None else ''
        return os.path.join(self._dfsdir, dfid, fname)

    def _find_ids(self):
        return [self._id_from_dirname(fname)
                for fname in os.listdir(self._dfsdir)]

    @property
    def filetype(self):
        return self._filetype

    @property
    def ids(self):
        if self._ids is None or len(self._ids) == 0:
            self._ids = self._find_ids()
        return self._ids

    def _all_paths(self):
        ret = []
        for dfid in self.ids:
            idpath = self._path(dfid)
            ret += [os.path.join(idpath, fname)
                    for fname in os.listdir(idpath)]
        return ret

    def __len__(self):
        return len(self.ids)

    def copy_from_csvs_dir(self, dirpath, endswith='.csv', **read_kwargs):
        fnames = [fname for fname in os.listdir(dirpath)
                  if fname.endswith(endswith)]
        for fname in fnames:
            path = os.path.join(dirpath, fname)
            df = pd.read_csv(path, **read_kwargs)
            if fname.endswith('.csv'):
                fname = fname[:-4]
            self[self._id_from_dirname(fname)] = df
            # print("df fname:", fname)
            # print("df dtypes:\n", df.dtypes)
            # df_hat = self[self._id_from_dirname(fname)]
            # print("df hat fname:", fname)
            # print("df hat dtypes:\n", df.dtypes)  # yep, same
        return self

    # TODO put in some caching logic so we don't actually have to touch
    # the filesystem each time

    def _cols_stored_for_dfid(self, dfid):
        return [self._rm_endswith(fname)
                for fname in os.listdir(self._path(dfid))]

    # def __getitem__(self, dfid, cols=None):
    def __getitem__(self, dfid_and_maybe_cols):
        if isinstance(dfid_and_maybe_cols, tuple):
            dfid, cols = dfid_and_maybe_cols   # 2 args
        else:
            dfid = dfid_and_maybe_cols
            cols = None

        if cols is None:
            cols = self._cols_stored_for_dfid(dfid)
        ret = {}
        # print("cols: ", cols)
        if isinstance(cols, str):
            cols = [cols]  # was actually just one col
        for col in cols:
            path = self._path(dfid, col)
            if not os.path.exists(path):
                # TODO add option to throw here if path not found
                continue  # just omit instead of crashing
            ret[col] = self._read_col_from_path(path)
        return pd.DataFrame.from_dict(ret)

    # def __setitem__(self, dfid_and_maybe_cols, df_or_array):
    #     if isinstance(dfid_and_maybe_cols, tuple):
    #         dfid, cols = dfid_and_maybe_cols   # 2 args
    #     else:
    #         dfid = dfid_and_maybe_cols
    #         cols = None
    #     if cols is None:
    #         cols = df.columns

    def __setitem__(self, dfid, df):
        dfid_path = self._path(dfid)
        if not os.path.exists(dfid_path):
            os.mkdir(dfid_path)
        for col in df:
            self._write_col_to_path(self._path(dfid, col), df[col])

    @abc.abstractmethod
    def _read_col_from_path(self, path):
        pass

    @abc.abstractmethod
    def _write_col_to_path(self, path, values):
        pass

    def file_sizes(self):
        all_dfids = []
        all_cols = []
        all_sizes = []
        # for path in self._all_paths():
        for dfid in self.ids:
            # print("reading sizes of id: ", dfid)
            cols = self._cols_stored_for_dfid(dfid)
            # print("cols: ", cols)
            # import sys; sys.exit()
            for col in cols:
                # print("reading size of col: ", col)
                path = self._path(dfid, col)
                sz = os.path.getsize(path)
                all_dfids.append(dfid)
                all_cols.append(col)
                all_sizes.append(sz)
        return pd.DataFrame.from_dict({
            'dfid': all_dfids, 'col': all_cols, 'nbytes': all_sizes})

    def equals(self, other, raise_error=False):
        our_ids = self.ids
        other_ids = other.ids
        try:
            assert len(our_ids) == len(other_ids)
            assert np.all(np.sort(our_ids) == np.sort(other_ids))

            for dfid in our_ids:
                our_cols = self._cols_stored_for_dfid(dfid)
                other_cols = other._cols_stored_for_dfid(dfid)
                assert len(our_cols) == len(other_cols)
                assert np.all(np.sort(our_cols) == np.sort(other_cols))
                for col in our_cols:
                    our_vals = self[dfid, col]
                    other_vals = other[dfid, col]
                    assert len(our_vals) == len(other_vals)
                    # if col == 'c':
                    #     print("dfid, col = ", dfid, col)
                    #     print("our vals:", our_vals)
                    #     print("other vals:", other_vals)
                    assert np.allclose(our_vals, other_vals)
                    # assert np.allclose(
                    #     np.sort(our_vals), np.sort(other_vals))
        except AssertionError as e:
            if raise_error:
                raise e
            return False

        return True

    def clone_into(self, other):
        for dfid in self.ids:
            # print(f"cloning dfid: '{dfid}'")
            other[dfid] = self[dfid]
            # print(f"cloning dfid: '{dfid}'")
            # import time; time.sleep(1)
            # for col in self._cols_stored_for_dfid(dfid):
            #     print(f"col: '{col}'")
            #     other[dfid, col] = self[dfid, col]

    def copy(self, dfsdir=None):
        other = make_dfset(
            dfsdir=dfsdir, filetype=self.filetype,
            read_kwargs=self.read_kwargs.copy(),
            write_kwargs=self.write_kwargs.copy())
        self.clone_into(other)
        return other

    # def nfiles(self):
    #     return len(self._all_paths())

    # def __getitem__(self, dfid, cols=None):
    #     path = self._path_from_id(dfid)
    #     if self._filetype == 'csv':
    #         df = pd.read_csv(path, **self.read_kwargs)
    #         if cols is not None:
    #             return df[cols]
    #         return df
    #     elif self._filetype == 'parquet':
    #         return pd.read_parquet(path, columns=cols, **self.read_kwargs)


class CsvDfSet(BaseDfSet):
    # XXX only supports float, since doesn't preserve dtype

    def __init__(self, *args, **kwargs):
        kwargs['filetype'] = 'csv'
        super().__init__(*args, **kwargs)
        self.read_kwargs.setdefault('delimiter', ',')
        self.write_kwargs.setdefault('delimiter', ',')

    def _read_col_from_path(self, path):
        # print("reading from path: ", path)
        return np.loadtxt(path, **self.read_kwargs)

    def _write_col_to_path(self, path, values):
        # print("writing to path: ", path)
        np.savetxt(path, np.asarray(values), **self.write_kwargs)


class NpyDfSet(BaseDfSet):

    def __init__(self, *args, **kwargs):
        kwargs['filetype'] = 'npy'
        super().__init__(*args, **kwargs)
        # compression is a good idea, but messes up file size measurements
        # self.write_kwargs.setdefault('compression', None)

    def _read_col_from_path(self, path):
        # print("reading from path: ", path)
        return np.load(path, **self.read_kwargs)

    def _write_col_to_path(self, path, values):
        # print("writing to path: ", path)
        np.save(path, np.asarray(values), **self.write_kwargs)


class ParquetDfSet(BaseDfSet):

    def __init__(self, *args, **kwargs):
        kwargs['filetype'] = 'parquet'
        super().__init__(*args, **kwargs)
        self.write_kwargs.setdefault('compression', 'snappy')
        self.write_kwargs.setdefault('index', False)

    def _read_col_from_path(self, path):
        # print("reading from path: ", path)
        return pd.read_parquet(path, **self.read_kwargs)['_']

    def _write_col_to_path(self, path, values):
        # print("writing to path: ", path)
        # df = pd.Series.from_array(values)
        # df = pd.DataFrame([pd.Series.from_array(values)])
        # print("values shape", values.shape)
        df = pd.DataFrame.from_dict({'_': values})
        return df.to_parquet(path, **self.write_kwargs)


class H5DfSet(BaseDfSet):
    # it would be a better use of h5 / less load on the filesystem if we put
    # everything in one h5 file; but for the purpose of assessing compression
    # ratios, having separate files for each (dfid, col) makes life way easier

    def __init__(self, *args, **kwargs):
        kwargs['filetype'] = 'h5'
        super().__init__(*args, **kwargs)
        # we're mostly using h5 as a way to get bzip2
        self.write_kwargs.setdefault('complib', 'bzip2')
        self.write_kwargs.setdefault('complevel', 9)

    def _read_col_from_path(self, path):
        # print("reading from path: ", path)
        # return pd.from_parquet(path, **self.read_kwargs)
        return pd.read_hdf(path, mode='r', **self.read_kwargs)['_']

    def _write_col_to_path(self, path, values):
        # print("writing to path: ", path)
        # df = pd.Series.from_array(values)
        df = pd.DataFrame.from_dict({'_': values})
        return df.to_hdf(path, key='_', mode='w', **self.write_kwargs)


def make_dfset(filetype, dfsdir=None, csvsdir=None, **kwargs):
    if dfsdir is None:
        dfsdir = tempfile.mkdtemp()

    if filetype == 'csv':
        dfs = CsvDfSet(dfsdir, **kwargs)
    elif filetype == 'npy':
        dfs = NpyDfSet(dfsdir, **kwargs)
    elif filetype == 'parquet':
        dfs = ParquetDfSet(dfsdir, **kwargs)
    elif filetype == 'h5':
        dfs = H5DfSet(dfsdir, **kwargs)
    else:
        raise ValueError(f"unrecognized filetype: '{filetype}'")

    if csvsdir is not None:
        dfs.copy_from_csvs_dir(csvsdir)
    return dfs

    # def __getitem__(self, dfid, cols=None):
    #     pass # TODO

    # def __setitem__(self, dfid, df):
    #     for col in df:
    #         pass # TODO
    #         # self._write_col_to_path(self._path(dfid, col), df[col])