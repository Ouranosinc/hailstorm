from xclim import streamflow


def test_base_flow_index(ndq_series):
    out = streamflow.base_flow_index(ndq_series, freq='YS')
    assert out.attrs['units'] == ''


def test_fa(ndq_series):
    out = streamflow.freq_analysis(ndq_series, mode='max', t=[2, 5], dist='gamma', season='DJF')
    assert out.long_name == 'N-year return period max winter 1-day flow'


def test_stats(ndq_series):
    out = streamflow.stats(ndq_series, freq='YS', op='min', season='MAM')
    assert out.attrs['units'] == 'm^3 s-1'


def test_qdoy_max(ndq_series):
    out = streamflow.doy_qmax(ndq_series, freq='YS', season='JJA')
    assert out.attrs['units'] == ''
