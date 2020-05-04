import functools

import pandas as pd
import requests

from libs.datasets import data_source
from libs.datasets import AggregationLevel
from libs.datasets import CommonFields
from libs.datasets import CommonIndexFields
from libs import us_state_abbrev


class PyseirOutput(data_source.DataSource):

    class Fields(object):
        DAY_NUM = 'day_num'      # Index Column. Generally not the same between simulations.
        DATE = "date"            # Date in the timeseries.
        TOTAL = "total"          # All people in the model. This should always be population.
        TOTAL_SUSCEPTIBLE = "susceptible"
        EXPOSED = "exposed"
        INFECTED = "infected"
        # Infected by not hospitalized
        INFECTED_A = "infected_a"

        # Hospitalized but not ICU
        INFECTED_B = "infected_b"
        # In ICU
        INFECTED_C = "infected_c"

        # Total hospitalized
        ALL_HOSPITALIZED = "all_hospitalized"

        # Total infected (in hospital or not)
        ALL_INFECTED = "all_infected"

        DEAD = "dead"

        # General bed capacity excluding ICU beds.
        BEDS = "beds"

        CUMULATIVE_INFECTED = "cumulative_infected"

        # Effective reproduction number at time t.
        Rt = 'Rt'

        # 90% confidence interval at time t.
        Rt_ci90 = 'Rt_ci90'

        CURRENT_VENTILATED = 'current_ventilated'

        POPULATION = "population"

        ICU_BED_CAPACITY = "icu_bed_capacity"

        VENTILATOR_CAPACITY = "ventilator_capacity"

        RT_INDICATOR = 'Rt_indicator'

        RT_INDICATOR_CI90 = 'Rt_indicator_ci90'

        FIPS = "fips"
        STATE = "state"
        AGGREGATE_LEVEL = "aggregate_level"
        COUNTRY = "country"
        INTERVENTION = "intervention"

    INDEX_FIELD_MAP = {
        CommonIndexFields.COUNTRY: Fields.COUNTRY,
        CommonIndexFields.STATE: Fields.STATE,
        CommonIndexFields.FIPS: Fields.FIPS,
        CommonIndexFields.AGGREGATE_LEVEL: Fields.AGGREGATE_LEVEL,
    }

    COMMON_FIELD_MAP = {
        CommonFields.INTERVENTION: Fields.INTERVENTION,
    }

    def _read_json_as_df(path):
        # TODO: read this from a dataset class
        df = pd.DataFrame.from_records(
            simplejson.load(open(path, "r")),
            columns=CAN_MODEL_OUTPUT_SCHEMA,
        )
        df["date"] = pd.to_datetime(df.date, format="%m/%d/%y")
        df["all_hospitalized"] = df["all_hospitalized"].astype("int")
        df["beds"] = df["beds"].astype("int")
        df["dead"] = df["dead"].astype("int")
        df["population"] = df["population"].astype("int")
        df["Rt"] = df["Rt"].astype("float")
        df["Rt_ci90"] = df["Rt_ci90"].astype("float")
        df["Rt_indicator"] = df["Rt_indicator"].astype("float")
        df["Rt_indicator_ci90"] = df["Rt_indicator_ci90"].astype("float")
        df["short_fall"] = df.apply(_calc_short_fall, axis=1)
        df["new_deaths"] = df.dead - df.dead.shift(1)

        # Rt_indicator is NaN sometimes
        df.fillna(0, inplace=True)
        return df

    @classmethod
    def standardize_data(cls, data) -> pd.DataFrame:
        data[cls.Fields.AGGREGATE_LEVEL] = AggregationLevel.STATE.value
        data[cls.Fields.COUNTRY] = "USA"
        data[cls.Fields.FIPS] = data[cls.Fields.STATE].map(
            us_state_abbrev.ABBREV_US_FIPS
        )
        return data

    @classmethod
    @functools.lru_cache(None)
    def local(cls):
        interventions = requests.get(cls.INTERVENTIONS_URL).json()

        columns = [cls.Fields.STATE, cls.Fields.INTERVENTION]

        data = pd.DataFrame(list(interventions.items()), columns=columns)
        data = cls.standardize_data(data)
        return cls(data)