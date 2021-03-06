import os

import cftime
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from numpy.testing import assert_array_equal
from xarray.coding.cftimeindex import CFTimeIndex

from xclim.core.calendar import (
    adjust_doy_calendar,
    convert_calendar,
    date_range,
    datetime_to_decimal_year,
    days_in_year,
    ensure_cftime_array,
    get_calendar,
    interp_calendar,
    max_doy,
    percentile_doy,
    time_bnds,
)
from xclim.testing import open_dataset


@pytest.fixture(
    params=[dict(start="2004-01-01T12:07:01", periods=27, freq="3MS")], ids=["3MS"]
)
def time_range_kwargs(request):
    return request.param


@pytest.fixture()
def datetime_index(time_range_kwargs):
    return pd.date_range(**time_range_kwargs)


@pytest.fixture()
def cftime_index(time_range_kwargs):
    return xr.cftime_range(**time_range_kwargs)


def da(index):
    return xr.DataArray(
        np.arange(100.0, 100.0 + index.size), coords=[index], dims=["time"]
    )


@pytest.mark.parametrize(
    "freq", ["3A-MAY", "5Q-JUN", "7M", "6480H", "302431T", "23144781S"]
)
def test_time_bnds(freq, datetime_index, cftime_index):
    da_datetime = da(datetime_index).resample(time=freq)
    da_cftime = da(cftime_index).resample(time=freq)

    cftime_bounds = time_bnds(da_cftime, freq=freq)
    cftime_starts, cftime_ends = zip(*cftime_bounds)
    cftime_starts = CFTimeIndex(cftime_starts).to_datetimeindex()
    cftime_ends = CFTimeIndex(cftime_ends).to_datetimeindex()

    # cftime resolution goes down to microsecond only, code below corrects
    # that to allow for comparison with pandas datetime
    cftime_ends += np.timedelta64(999, "ns")
    datetime_starts = da_datetime._full_index.to_period(freq).start_time
    datetime_ends = da_datetime._full_index.to_period(freq).end_time

    assert_array_equal(cftime_starts, datetime_starts)
    assert_array_equal(cftime_ends, datetime_ends)


def test_percentile_doy(tas_series):
    tas = tas_series(np.arange(365), start="1/1/2001")
    tas = xr.concat((tas, tas), "dim0")
    p1 = percentile_doy(tas, window=5, per=0.5)
    assert p1.sel(dayofyear=3, dim0=0).data == 2
    assert p1.attrs["units"] == "K"


def test_percentile_doy_nan(tas_series):
    tas = tas_series(np.arange(365), start="1/1/2001")
    tas = tas.where(tas.time.dt.dayofyear != 2)
    tas = xr.concat((tas, tas), "dim0")
    pnan = percentile_doy(tas, window=5, per=0.5)
    assert pnan.sel(dayofyear=3, dim0=0).data == 2.5
    assert pnan.attrs["units"] == "K"


def test_adjust_doy_360_to_366():
    source = xr.DataArray(np.arange(360), coords=[np.arange(1, 361)], dims="dayofyear")
    time = pd.date_range("2000-01-01", "2001-12-31", freq="D")
    target = xr.DataArray(np.arange(len(time)), coords=[time], dims="time")

    out = adjust_doy_calendar(source, target)

    assert out.sel(dayofyear=1) == source.sel(dayofyear=1)
    assert out.sel(dayofyear=366) == source.sel(dayofyear=360)


@pytest.mark.parametrize(
    "file,cal,maxdoy",
    [
        (
            (
                "CanESM2_365day",
                "pr_day_CanESM2_rcp85_r1i1p1_na10kgrid_qm-moving-50bins-detrend_2095.nc",
            ),
            "noleap",
            365,
        ),
        (
            (
                "HadGEM2-CC_360day",
                "pr_day_HadGEM2-CC_rcp85_r1i1p1_na10kgrid_qm-moving-50bins-detrend_2095.nc",
            ),
            "360_day",
            360,
        ),
        (("NRCANdaily", "nrcan_canada_daily_pr_1990.nc"), "default", 366),
    ],
)
def test_get_calendar(file, cal, maxdoy):
    with open_dataset(os.path.join(*file)) as ds:
        out_cal = get_calendar(ds)
        assert cal == out_cal
        assert max_doy[cal] == maxdoy


@pytest.mark.parametrize(
    "obj,cal",
    [
        ([pd.Timestamp.now()], "default"),
        (pd.Timestamp.now(), "default"),
        (cftime.DatetimeAllLeap(2000, 1, 1), "all_leap"),
        (np.array([cftime.DatetimeNoLeap(2000, 1, 1)]), "noleap"),
    ],
)
def test_get_calendar_nonxr(obj, cal):
    assert get_calendar(obj) == cal


@pytest.mark.parametrize(
    "source,target,target_as_str,freq",
    [
        ("standard", "noleap", True, "D"),
        ("noleap", "default", True, "D"),
        ("noleap", "all_leap", False, "D"),
        ("proleptic_gregorian", "noleap", False, "4H"),
        ("default", "noleap", True, "4H"),
    ],
)
def test_convert_calendar(source, target, target_as_str, freq):
    src = xr.DataArray(
        date_range("2004-01-01", "2004-12-31", freq=freq, calendar=source),
        dims=("time",),
        name="time",
    )
    da_src = xr.DataArray(
        np.linspace(0, 1, src.size), dims=("time",), coords={"time": src}
    )
    tgt = xr.DataArray(
        date_range("2004-01-01", "2004-12-31", freq=freq, calendar=target),
        dims=("time",),
        name="time",
    )

    conv = convert_calendar(da_src, target if target_as_str else tgt)

    assert get_calendar(conv) == target

    if target_as_str and max_doy[source] < max_doy[target]:
        assert conv.size == src.size
    elif not target_as_str:
        assert conv.size == tgt.size

        assert conv.isnull().sum() == max(max_doy[target] - max_doy[source], 0)


@pytest.mark.parametrize(
    "source,target,freq",
    [
        ("standard", "360_day", "D"),
        ("360_day", "default", "D"),
        ("proleptic_gregorian", "360_day", "4H"),
    ],
)
@pytest.mark.parametrize("align_on", ["date", "year"])
def test_convert_calendar_360_days(source, target, freq, align_on):
    src = xr.DataArray(
        date_range("2004-01-01", "2004-12-30", freq=freq, calendar=source),
        dims=("time",),
        name="time",
    )
    da_src = xr.DataArray(
        np.linspace(0, 1, src.size), dims=("time",), coords={"time": src}
    )

    conv = convert_calendar(da_src, target, align_on=align_on)

    assert get_calendar(conv) == target

    if align_on == "date":
        np.testing.assert_array_equal(
            conv.time.resample(time="M").last().dt.day,
            [30, 29, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30],
        )
    elif target == "360_day":
        np.testing.assert_array_equal(
            conv.time.resample(time="M").last().dt.day,
            [30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 29],
        )
    else:
        np.testing.assert_array_equal(
            conv.time.resample(time="M").last().dt.day,
            [30, 29, 30, 30, 31, 30, 30, 31, 30, 31, 29, 31],
        )
    if source == "360_day" and align_on == "year":
        assert conv.size == 360 if freq == "D" else 360 * 4
    else:
        assert conv.size == 359 if freq == "D" else 359 * 4


@pytest.mark.parametrize(
    "source,target,freq",
    [
        ("standard", "noleap", "D"),
        ("noleap", "default", "4H"),
        ("noleap", "all_leap", "M"),
        ("360_day", "noleap", "D"),
        ("noleap", "360_day", "D"),
    ],
)
def test_convert_calendar_missing(source, target, freq):
    src = xr.DataArray(
        date_range(
            "2004-01-01",
            "2004-12-31" if source != "360_day" else "2004-12-30",
            freq=freq,
            calendar=source,
        ),
        dims=("time",),
        name="time",
    )
    da_src = xr.DataArray(
        np.linspace(0, 1, src.size), dims=("time",), coords={"time": src}
    )
    out = convert_calendar(da_src, target, missing=np.nan, align_on="date")
    assert xr.infer_freq(out.time) == freq
    if source == "360_day":
        assert out.time[-1].dt.day == 31


@pytest.mark.parametrize(
    "source,target",
    [
        ("standard", "noleap"),
        ("noleap", "default"),
        ("standard", "360_day"),
        ("360_day", "gregorian"),
        ("noleap", "all_leap"),
        ("360_day", "noleap"),
    ],
)
def test_interp_calendar(source, target):
    src = xr.DataArray(
        date_range("2004-01-01", "2004-07-30", freq="D", calendar=source),
        dims=("time",),
        name="time",
    )
    tgt = xr.DataArray(
        date_range("2004-01-01", "2004-07-30", freq="D", calendar=target),
        dims=("time",),
        name="time",
    )
    da_src = xr.DataArray(
        np.linspace(0, 1, src.size), dims=("time",), coords={"time": src}
    )
    conv = interp_calendar(da_src, tgt)

    assert conv.size == tgt.size
    assert get_calendar(conv) == target

    np.testing.assert_almost_equal(conv.max(), 1, 2)
    assert conv.min() == 0


@pytest.mark.parametrize(
    "inp,calout",
    [
        (
            xr.DataArray(
                date_range("2004-01-01", "2004-01-10", freq="D"),
                dims=("time",),
                name="time",
            ),
            "gregorian",
        ),
        (date_range("2004-01-01", "2004-01-10", freq="D"), "gregorian"),
        (
            xr.DataArray(date_range("2004-01-01", "2004-01-10", freq="D")).values,
            "gregorian",
        ),
        (date_range("2004-01-01", "2004-01-10", freq="D"), "gregorian"),
        (date_range("2004-01-01", "2004-01-10", freq="D", calendar="julian"), "julian"),
    ],
)
def test_ensure_cftime_array(inp, calout):
    out = ensure_cftime_array(inp)
    assert out[0].calendar == calout


@pytest.mark.parametrize(
    "year,calendar,exp",
    [
        (2004, "standard", 366),
        (2004, "noleap", 365),
        (2004, "all_leap", 366),
        (1500, "default", 365),
        (1500, "gregorian", 366),
        (1500, "proleptic_gregorian", 365),
        (2030, "360_day", 360),
    ],
)
def test_days_in_year(year, calendar, exp):
    assert days_in_year(year, calendar) == exp


@pytest.mark.parametrize(
    "source_cal, exp180",
    [
        ("standard", 0.49180328),
        ("default", 0.49180328),
        ("noleap", 0.49315068),
        ("all_leap", 0.49180328),
        ("360_day", 0.5),
        (None, 0.49180328),
    ],
)
def test_datetime_to_decimal_year(source_cal, exp180):
    times = xr.DataArray(
        date_range(
            "2004-01-01", "2004-12-30", freq="D", calendar=source_cal or "default"
        ),
        dims=("time",),
        name="time",
    )
    decy = datetime_to_decimal_year(times, calendar=source_cal)
    np.testing.assert_almost_equal(decy[180] - 2004, exp180)
