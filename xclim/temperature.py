from . utils import Indicator
from . import indices
from . import checks

class TxMax(Indicator):
    identifier='tx_max'
    required_units = 'K'
    long_name = 'Maximum temperature'
    standard_name = 'tasmax'
    description = 'Maximum daily maximum temperature over period.'
    keywords = ''

    def compute(self, tasmax, freq='YS'):
        return indices.tx_max(tasmax, freq)

    def convert_units(self, tas):
        return (checks.convert_temp(tas, self.required_units), )

    def cfprobe(self, tas):
        checks.check_valid(tas, 'cell_methods', 'time: maximum within days')
        checks.check_valid(tas, 'standard_name', 'air_temperature')

    def validate(self, tas):
        checks.assert_daily(tas)

    def missing(self, tas, freq):
        """An aggregated value is missing if any value in the group is missing."""
        g = tas.notnull().resample(time=freq)
        return g.sum(dim='time')





