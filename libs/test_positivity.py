import dataclasses
import pathlib
from itertools import chain
from typing import List
from typing import Sequence

import pandas as pd

from covidactnow.datapublic.common_fields import CommonFields, FieldName

from libs.datasets import timeseries
from libs.datasets.timeseries import MultiRegionTimeseriesDataset


@dataclasses.dataclass
class Method:
    """A method of calculating test positivity"""

    name: str
    numerator: FieldName
    denominator: FieldName

    def calculate(self, delta_df: pd.DataFrame) -> pd.DataFrame:
        assert delta_df.columns.names == [CommonFields.DATE]
        assert delta_df.index.names == [CommonFields.VARIABLE, CommonFields.LOCATION_ID]
        # delta_df has the field name as the first level of the index. delta_df.loc[field, :] returns a
        # DataFrame without the field label so operators such as `/` are calculated for each
        # region/state and date.
        return delta_df.loc[self.numerator, :] / delta_df.loc[self.denominator, :]


TEST_POSITIVITY_METHODS = (
    Method(
        "positiveCasesViral_totalTestEncountersViral",
        CommonFields.POSITIVE_CASES_VIRAL,
        CommonFields.TOTAL_TEST_ENCOUNTERS_VIRAL,
    ),
    Method(
        "positiveTestsViral_totalTestsViral",
        CommonFields.POSITIVE_TESTS_VIRAL,
        CommonFields.TOTAL_TESTS_VIRAL,
    ),
    Method(
        "positiveCasesViral_totalTestsViral",
        CommonFields.POSITIVE_CASES_VIRAL,
        CommonFields.TOTAL_TESTS_VIRAL,
    ),
    Method(
        "positiveTests_totalTestsViral", CommonFields.POSITIVE_TESTS, CommonFields.TOTAL_TESTS_VIRAL
    ),
    Method(
        "positiveCasesViral_totalTestsPeopleViral",
        CommonFields.POSITIVE_CASES_VIRAL,
        CommonFields.TOTAL_TESTS_PEOPLE_VIRAL,
    ),
    Method(
        "positiveCasesViral_totalTestResults",
        CommonFields.POSITIVE_CASES_VIRAL,
        CommonFields.TOTAL_TESTS,
    ),
)


@dataclasses.dataclass
class AllMethods:
    """The result of calculating all test positivity methods for all regions"""

    # Test positivity calculated in all valid methods for each region
    all_methods_timeseries: pd.DataFrame

    # Test positivity using the best available method for each region
    test_positivity: MultiRegionTimeseriesDataset

    @staticmethod
    def run(
        metrics_in: MultiRegionTimeseriesDataset,
        methods: Sequence[Method] = TEST_POSITIVITY_METHODS,
        diff_days: int = 7,
        recent_days: int = 14,
    ) -> "AllMethods":
        ts_value_cols = list(
            set(chain.from_iterable((method.numerator, method.denominator) for method in methods))
        )
        assert set(ts_value_cols).issubset(set(metrics_in.data.columns))

        input_long = metrics_in.timeseries_long(ts_value_cols).set_index(
            [CommonFields.VARIABLE, CommonFields.LOCATION_ID, CommonFields.DATE]
        )[CommonFields.VALUE]
        dates = input_long.index.get_level_values(CommonFields.DATE)
        start_date = dates.min()
        end_date = dates.max()
        input_date_range = pd.date_range(start=start_date, end=end_date)
        recent_date_range = pd.date_range(end=end_date, periods=recent_days).intersection(
            input_date_range
        )
        input_wide = (
            input_long.unstack(CommonFields.DATE)
            .reindex(columns=input_date_range)
            .rename_axis(columns=CommonFields.DATE)
        )
        # This calculates the difference only when the cumulative value is a real value `diff_days` apart.
        # It looks like our input data has few or no holes so this works well enough.
        diff_df = input_wide.diff(periods=diff_days, axis=1)

        all_wide = (
            pd.concat(
                {method.name: method.calculate(diff_df) for method in methods},
                names=[CommonFields.VARIABLE],
            )
            .reorder_levels([CommonFields.LOCATION_ID, CommonFields.VARIABLE])
            # Drop empty timeseries
            .dropna("index", "all")
            .sort_index()
        )

        method_cat_type = pd.CategoricalDtype(
            categories=[method.name for method in methods], ordered=True
        )

        has_recent_data = all_wide.loc[:, recent_date_range].notna().any(axis=1)
        all_recent_data = all_wide.loc[has_recent_data, :].reset_index()
        all_recent_data[CommonFields.VARIABLE] = all_recent_data[CommonFields.VARIABLE].astype(
            method_cat_type
        )
        first = all_recent_data.groupby(CommonFields.LOCATION_ID).first()
        provenance = first[CommonFields.VARIABLE].astype(str).rename(CommonFields.PROVENANCE)
        provenance.index = pd.MultiIndex.from_product(
            [provenance.index, ["positivity"]],
            names=[CommonFields.LOCATION_ID, CommonFields.VARIABLE],
        )
        positivity = first.drop(columns=[CommonFields.VARIABLE])

        test_positivity = MultiRegionTimeseriesDataset.from_timeseries_df(
            positivity.stack().rename("positivity").reset_index(), provenance=provenance
        )

        return AllMethods(all_methods_timeseries=all_wide, test_positivity=test_positivity)

    def write(self, csv_path: pathlib.Path):
        self.all_methods_timeseries.to_csv(
            csv_path, date_format="%Y-%m-%d", index=True, float_format="%.05g",
        )