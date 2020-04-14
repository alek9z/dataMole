import pandas as pd
from data_preprocessor.data import Loader


class CsvLoader(Loader):
    def read(self, **kwargs):
        return Frame(pd.read_csv(**kwargs))
