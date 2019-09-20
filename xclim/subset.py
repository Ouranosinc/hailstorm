import warnings
from typing import List

import numpy as np
import xarray
from pyproj import Geod

__all__ = ["subset_bbox", "subset_gridpoint", "subset_time"]


def check_dates(func):
    def func_checker(*args, **kwargs):
        """
        A decorator to reformat the deprecated `start_yr` and `end_yr` calls to subset functions and return
         `start_date` and `end_date` to kwargs. Deprecation warnings are raised for deprecated usage.
        """

        _DEPRECATION_MESSAGE = (
            '"start_yr" and "end_yr" (type: int) are being deprecated. Temporal subsets will soon exclusively'
            ' support "start_date" and "end_date" (type: str) using formats of "%Y", "%Y-%m" or "%Y-%m-%d".'
        )

        if "start_yr" in kwargs:
            warnings.warn(_DEPRECATION_MESSAGE, FutureWarning, stacklevel=3)
            if kwargs["start_yr"] is not None:
                kwargs["start_date"] = str(kwargs.pop("start_yr"))
            elif kwargs["start_yr"] is None:
                kwargs["start_date"] = None
        elif "start_date" not in kwargs:
            kwargs["start_date"] = None

        if "end_yr" in kwargs:
            if kwargs["end_yr"] is not None:
                warnings.warn(_DEPRECATION_MESSAGE, FutureWarning, stacklevel=3)
                kwargs["end_date"] = str(kwargs.pop("end_yr"))
            elif kwargs["end_yr"] is None:
                kwargs["end_date"] = None
        elif "end_date" not in kwargs:
            kwargs["end_date"] = None

        return func(*args, **kwargs)

    return func_checker


def check_lons(func):
    def func_checker(*args, **kwargs):
        """
        A decorator to reformat user-specified lon values based on the lon dimensions of a supplied xarray
         DataSet or DataArray. Returns a numpy array of reformatted `lon` or `lon_bnds` in kwargs
         with min() and max() values.
        """

        if "lon_bnds" in kwargs:
            lon = "lon_bnds"
        elif "lon" in kwargs:
            lon = "lon"
        else:
            return func(*args, **kwargs)

        if isinstance(args[0], (xarray.DataArray, xarray.Dataset)):
            if kwargs[lon] is None:
                kwargs[lon] = np.asarray(args[0].lon.min(), args[0].lon.max())
            else:
                kwargs[lon] = np.asarray(kwargs[lon])
            if np.all(args[0].lon > 0) and np.any(kwargs[lon] < 0):
                if isinstance(kwargs[lon], float):
                    kwargs[lon] += 360
                else:
                    kwargs[lon][kwargs[lon] < 0] += 360
            if np.all(args[0].lon < 0) and np.any(kwargs[lon] > 0):
                if isinstance(kwargs[lon], float):
                    kwargs[lon] -= 360
                else:
                    kwargs[lon][kwargs[lon] < 0] -= 360

        return func(*args, **kwargs)

    return func_checker


@check_lons
@check_dates
def subset_bbox(da, lon_bnds=None, lat_bnds=None, start_date=None, end_date=None):
    """Subset a datarray or dataset spatially (and temporally) using a lat lon bounding box and date selection.

    Return a subsetted data array for grid points falling within a spatial bounding box
    defined by longitude and latitudinal bounds and for dates falling within provided bounds.

    In the case of a lat-lon rectilinear grid, this simply returns the

    Parameters
    ----------
    da : Union[xarray.DataArray, xarray.Dataset]
      Input data.
    lon_bnds : Union[numpy.array, List[float]]
      List of minimum and maximum longitudinal bounds. Optional. Defaults to all longitudes in original data-array.
    lat_bnds :  List[float]
      List of minimum and maximum latitudinal bounds. Optional. Defaults to all latitudes in original data-array.
    start_date : str
      Start date of the subset.
      Date string format -- can be year ("%Y"), year-month ("%Y-%m") or year-month-day("%Y-%m-%d").
      Defaults to first day of input data-array.
    end_date : str
      End date of the subset.
      Date string format -- can be year ("%Y"), year-month ("%Y-%m") or year-month-day("%Y-%m-%d").
      Defaults to last day of input data-array.
    start_yr : int
      Deprecated --
      First year of the subset. Defaults to first year of input data-array.
    end_yr : int
      Deprecated --
      Last year of the subset. Defaults to last year of input data-array.


    Returns
    -------
    xarray.DataArray or xarray.DataSet
      subsetted data array or dataset

    Examples
    --------
    >>> from xclim import subset
    >>> ds = xr.open_dataset('pr.day.nc')
    Subset lat lon and years
    >>> prSub = subset.subset_bbox(ds.pr, lon_bnds=[-75,-70],lat_bnds=[40,45],start_yr='1990',end_yr='1999')
    Subset data array lat, lon and single year
    >>> prSub = subset.subset_bbox(ds.pr, lon_bnds=[-75,-70],lat_bnds=[40,45],start_yr='1990',end_yr='1990')
    Subset dataarray single year keep entire lon, lat grid
    >>> prSub = subset.subset_bbox(ds.pr,start_yr='1990',end_yr='1990') # one year only entire grid
    Subset multiple variables in a single dataset
    >>> ds = xr.open_mfdataset(['pr.day.nc','tas.day.nc'])
    >>> dsSub = subset.subset_bbox(ds,lon_bnds=[-75,-70],lat_bnds=[40,45],start_yr='1990',end_yr='1999')
     # Subset with year-month precision - Example subset 1990-03-01 to 1999-08-31 inclusively
    >>> prSub = subset.subset_time(ds.pr,lon_bnds=[-75,-70],lat_bnds=[40,45],start_date='1990-03',end_date='1999-08')
    # Subset with specific start_dates and end_dates
    >>> prSub = subset.subset_time(ds.pr,lon_bnds=[-75,-70],lat_bnds=[40,45],start_date='1990-03-13',end_date='1990-08-17')
    """
    # start_date, end_date = _check_times(
    #     start_date=start_date, end_date=end_date, start_yr=start_yr, end_yr=end_yr
    # )

    # Rectilinear case (lat and lon are the 1D dimensions)
    if ("lat" in da.dims) or ("lon" in da.dims):

        if "lat" in da.dims and lat_bnds is not None:
            lat_bnds = _check_desc_coords(coord=da.lat, bounds=lat_bnds, dim="lat")
            da = da.sel(lat=slice(*lat_bnds))

        if "lon" in da.dims and lon_bnds is not None:
            lon_bnds = _check_desc_coords(coord=da.lon, bounds=lon_bnds, dim="lon")
            da = da.sel(lon=slice(*lon_bnds))

    # Curvilinear case (lat and lon are coordinates, not dimensions)
    elif (("lat" in da.coords) and ("lon" in da.coords)) or (
        ("lat" in da.data_vars) and ("lon" in da.data_vars)
    ):

        # Define a bounding box along the dimensions
        # This is an optimization, a simple `where` would work but take longer for large hi-res grids.
        if lat_bnds is not None:
            lat_b = assign_bounds(lat_bnds, da.lat)
            lat_cond = in_bounds(lat_b, da.lat)
        else:
            lat_cond = True

        if lon_bnds is not None:
            lon_b = assign_bounds(lon_bnds, da.lon)
            lon_cond = in_bounds(lon_b, da.lon)
        else:
            lon_cond = True

        # Crop original array using slice, which is faster than `where`.
        ind = np.where(lon_cond & lat_cond)
        args = {}
        for i, d in enumerate(da.lat.dims):
            coords = da[d][ind[i]]
            args[d] = slice(coords.min(), coords.max())
        da = da.sel(**args)

        # Recompute condition on cropped coordinates
        if lat_bnds is not None:
            lat_cond = in_bounds(lat_b, da.lat)

        if lon_bnds is not None:
            lon_cond = in_bounds(lon_b, da.lon)

        # Mask coordinates outside the bounding box
        da = da.where(lon_cond & lat_cond, drop=True)

    else:
        raise (
            Exception(
                'subset_bbox() requires input data with "lon" and "lat" dimensions, coordinates or variables'
            )
        )

    if start_date or end_date:
        da = subset_time(da, start_date=start_date, end_date=end_date)

    return da


def assign_bounds(bounds, coord):
    """Replace unset boundaries by the minimum and maximum coordinates.

    Parameters
    ----------
    bounds : [Union[float, None], Union[float, None]]
      Boundaries.
    coord : xr.Coordinate
      Grid coordinates.

    Returns
    -------
    list
      Lower and upper grid boundaries.

    """
    if bounds[0] > bounds[1]:
        bounds = np.flip(bounds)
    bn, bx = bounds
    bn = bn if bn is not None else coord.min()
    bx = bx if bx is not None else coord.max()
    return bn, bx


def in_bounds(bounds, coord):
    """Check which coordinates are within the boundaries."""
    bn, bx = bounds
    return (coord >= bn) & (coord <= bx)


def _check_desc_coords(coord, bounds, dim):
    """if dataset coordinates are descending reverse bounds"""
    if np.all(coord.diff(dim=dim) < 0):
        bounds = np.flip(bounds)
    return bounds


@check_lons
@check_dates
def subset_gridpoint(da, lon=None, lat=None, start_date=None, end_date=None):
    """Extract a nearest gridpoint from datarray based on lat lon coordinate.
    Time series can optionally be subsetted by dates

    Return a subsetted data array (or dataset) for the grid point falling nearest the input
    longitude and latitudecoordinates. Optionally subset the data array for years falling
    within provided date bounds

    Parameters
    ----------
    da : Union[xarray.DataArray, xarray.DataSet]
      Input data.
    lon : float
      Longitude coordinate.
    lat:  float
      Latitude coordinate.
    start_date : str
      Start date of the subset.
      Date string format -- can be year ("%Y"), year-month ("%Y-%m") or year-month-day("%Y-%m-%d").
      Defaults to first day of input data-array.
    end_date : str
      End date of the subset.
      Date string format -- can be year ("%Y"), year-month ("%Y-%m") or year-month-day("%Y-%m-%d").
      Defaults to last day of input data-array.
    start_yr : int
      Deprecated --
      First year of the subset. Defaults to first year of input data-array.
    end_yr : int
      Deprecated --
      Last year of the subset. Defaults to last year of input data-array.

    Returns
    -------
    xarray.DataArray or xarray.DataSet
      Subsetted data array or dataset

    Examples
    --------
    >>> from xclim import subset
    >>> ds = xr.open_dataset('pr.day.nc')
    Subset lat lon point and multiple years
    >>> prSub = subset.subset_gridpoint(ds.pr, lon=-75,lat=45,start_date='1990',end_date='1999')
    Subset lat, lon point and single year
    >>> prSub = subset.subset_gridpoint(ds.pr, lon=-75,lat=45,start_date='1990',end_date='1999')
     Subset multiple variables in a single dataset
    >>> ds = xr.open_mfdataset(['pr.day.nc','tas.day.nc'])
    >>> dsSub = subset.subset_gridpoint(ds, lon=-75,lat=45,start_date='1990',end_date='1999')
    # Subset with year-month precision - Example subset 1990-03-01 to 1999-08-31 inclusively
    >>> prSub = subset.subset_time(ds.pr,lon=-75, lat=45, start_date='1990-03',end_date='1999-08')
    # Subset with specific start_dates and end_dates
    >>> prSub = subset.subset_time(ds.pr,lon=-75,lat=45, start_date='1990-03-13',end_date='1990-08-17')
    """

    # check if trying to subset lon and lat
    if lat is not None and lon is not None:
        # make sure input data has 'lon' and 'lat'(dims, coordinates, or data_vars)
        if hasattr(da, "lon") and hasattr(da, "lat"):
            dims = list(da.dims)

            # if 'lon' and 'lat' are present as data dimensions use the .sel method.
            if "lat" in dims and "lon" in dims:
                da = da.sel(lat=lat, lon=lon, method="nearest")
            else:
                g = Geod(ellps="WGS84")  # WGS84 ellipsoid - decent globaly
                lon1 = da.lon.values
                lat1 = da.lat.values
                shp_orig = lon1.shape
                lon1 = np.reshape(lon1, lon1.size)
                lat1 = np.reshape(lat1, lat1.size)
                # calculate geodesic distance between grid points and point of interest
                az12, az21, dist = g.inv(
                    lon1,
                    lat1,
                    np.broadcast_to(lon, lon1.shape),
                    np.broadcast_to(lat, lat1.shape),
                )
                dist = dist.reshape(shp_orig)
                iy, ix = np.unravel_index(np.argmin(dist, axis=None), dist.shape)
                xydims = [x for x in da.lon.dims]
                args = dict()
                args[xydims[0]] = iy
                args[xydims[1]] = ix
                da = da.isel(**args)
        else:
            raise (
                Exception(
                    'subset_gridpoint() requires input data with "lon" and "lat" coordinates or data variables.'
                )
            )

    if start_date or end_date:
        da = subset_time(da, start_date=start_date, end_date=end_date)

    return da


def subset_time(da, start_date=None, end_date=None):
    """Subset input data based on start and end years

    Return a subsetted data array (or dataset) for dates falling
    within provided bounds

    Parameters
    ----------
    da : xarray.DataArray or xarray.DataSet
      Input data.
    start_date : str
      Start date of the subset.
      Date string format -- can be year ("%Y"), year-month ("%Y-%m") or year-month-day("%Y-%m-%d").
      Defaults to first day of input data-array.
    end_date : str
      End date of the subset.
      Date string format -- can be year ("%Y"), year-month ("%Y-%m") or year-month-day("%Y-%m-%d").
      Defaults to last day of input data-array.

    Returns
    -------
    xarray.DataArray or xarray.DataSet
      Subsetted data array or dataset

    Examples
    --------
    >>> from xclim import subset
    >>> ds = xr.open_dataset('pr.day.nc')
    # Subset complete years
    >>> prSub = subset.subset_time(ds.pr,start_date='1990',end_date='1999')
    # Subset single complete year
    >>> prSub = subset.subset_time(ds.pr,start_date='1990',end_date='1990')
    # Subset multiple variables in a single dataset
    >>> ds = xr.open_mfdataset(['pr.day.nc','tas.day.nc'])
    >>> dsSub = subset.subset_time(ds,start_date='1990',end_date='1999')
    # Subset with year-month precision - Example subset 1990-03-01 to 1999-08-31 inclusively
    >>> prSub = subset.subset_time(ds.pr,start_date='1990-03',end_date='1999-08')
    # Subset with specific start_dates and end_dates
    >>> prSub = subset.subset_time(ds.pr,start_date='1990-03-13',end_date='1990-08-17')

    Notes
    TODO add notes about different calendar types. Avoid "%Y-%m-31". If you want complete month use only "%Y-%m".


    """

    if not start_date:
        # use string for first year only - .sel() will include all time steps
        start_date = da.time.min().dt.strftime("%Y").values
    if not end_date:
        # use string for last year only - .sel() will include all time steps
        end_date = da.time.max().dt.strftime("%Y").values

    if da.time.sel(time=start_date).min() > da.time.sel(time=end_date).max():
        raise ValueError("Start date is after end date.")

    return da.sel(time=slice(start_date, end_date))
