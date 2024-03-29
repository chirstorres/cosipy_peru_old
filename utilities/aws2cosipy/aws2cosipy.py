"""
 This file reads the input data (model forcing) and write the output to netcdf file
"""
import sys
import xarray as xr
import pandas as pd
import numpy as np
import time
import dateutil

#np.warnings.filterwarnings('ignore')

sys.path.append('../../')

from utilities.aws2cosipy.aws2cosipyConfig import *
from modules.radCor import correctRadiation

import argparse

def create_1D_input(cs_file, cosipy_file, static_file, start_date, end_date):
    """ This function creates an input dataset from an offered csv file with input point data
        Here you need to define how to interpolate the data.

        Please note, there should be only one header line in the file.

        Latest update: 
            Tobias Sauter 07.07.2019
    """

    print('-------------------------------------------')
    print('Create input \n')
    print('Read input file %s' % (cs_file))

    #-----------------------------------
    # Read data
    #-----------------------------------
    date_parser = lambda x: dateutil.parser.parse(x, ignoretz=True)
    df = pd.read_csv(cs_file,
       delimiter='\t', index_col=['TIMESTAMP'],
        parse_dates=['TIMESTAMP'], na_values='NAN',date_parser=date_parser)

    print(df[pd.isnull(df).any(axis=1)])
    df = df.fillna(method='ffill')
    print(df[pd.isnull(df).any(axis=1)])

    if (LWin_var not in df):
        df[LWin_var] = np.nan
    if (N_var not in df):
        df[N_var] = np.nan
    if (SNOWFALL_var not in df):
        df[SNOWFALL_var] = np.nan
 
    # Inproved function to sum dataframe columns which contain nan's
    def nansumwrapper(a, **kwargs):
        if np.isnan(a).all():
            return np.nan
        else:
            return np.nansum(a, **kwargs)

    col_list = [T2_var,RH2_var,U2_var,G_var,RRR_var,PRES_var,LWin_var,N_var,SNOWFALL_var]
    df = df[col_list]
    
    df = df.resample('1H').agg({T2_var:np.mean, RH2_var:np.mean, U2_var:np.mean, G_var:np.mean, PRES_var:np.mean, RRR_var:nansumwrapper, LWin_var:np.mean, N_var:np.mean, SNOWFALL_var:nansumwrapper})
    df = df.dropna(axis=1,how='all')
    print(df.head())

    #-----------------------------------
    # Select time slice
    #-----------------------------------
    if ((start_date != None) & (end_date !=None)): 
        df = df.loc[start_date:end_date]

    #-----------------------------------
    # Load static data
    #-----------------------------------
    dso = xr.Dataset()
    if (static_file):
        print('Read static file %s \n' % (static_file))
        ds = xr.open_dataset(static_file)
        ds = ds.sel(south_north=plat,west_east=plon,method='nearest')
        x, y = np.meshgrid(ds.west_east, ds.south_north)
    else:
        x, y = np.meshgrid(plon, plat)


    dso.coords['time'] = (('time'), df.index.values)
    dso.coords['lat'] = (('south_north','west_east'), y)
    dso.coords['lon'] = (('south_north','west_east'), x)

    #-----------------------------------
    # Order variables
    #-----------------------------------
    df[T2_var] = df[T2_var].apply(pd.to_numeric, errors='coerce')
    df[RH2_var] = df[RH2_var].apply(pd.to_numeric, errors='coerce')
    df[U2_var] = df[U2_var].apply(pd.to_numeric, errors='coerce')
    df[G_var] = df[G_var].apply(pd.to_numeric, errors='coerce')
    df[PRES_var] = df[PRES_var].apply(pd.to_numeric, errors='coerce')
    
    if (RRR_var in df):
        df[RRR_var] = df[RRR_var].apply(pd.to_numeric, errors='coerce')

    if (PRES_var not in df):
        df[PRES_var] = 660.00

    if (LWin_var not in df and N_var not in df):
        print("ERROR no longwave incoming or cloud cover data")
        sys.exit()
    elif (LWin_var in df):
        df[LWin_var] = df[LWin_var].apply(pd.to_numeric, errors='coerce')
    elif (N_var in df):
        df[N_var] = df[N_var].apply(pd.to_numeric, errors='coerce')

    if (SNOWFALL_var in df):
        df[SNOWFALL_var] = df[SNOWFALL_var].apply(pd.to_numeric, errors='coerce')

    #-----------------------------------
    # Get values from file
    #-----------------------------------
    if (in_K):
        T2 = df[T2_var].values         # Temperature
    else:
        T2 = df[T2_var].values + 273.16      

    RH2 = df[RH2_var].values       # Relative humdity
    U2 = df[U2_var].values          # Wind velocity
    G = df[G_var].values            # Incoming shortwave radiation
    PRES = df[PRES_var].values      # Pressure

    if (RRR_var in df):
        RRR = df[RRR_var].values       # Precipitation

    if(SNOWFALL_var in df):
        SNOWFALL = df[SNOWFALL_var].values      # Incoming longwave radiation

    if(LWin_var in df):
        LW = df[LWin_var].values      # Incoming longwave radiation

    if(N_var in df):
        N = df[N_var].values        # Cloud cover fraction

    # Change aspect to south==0, east==negative, west==positive
    if (static_file):
        ds['ASPECT'] = np.mod(ds['ASPECT']+180.0, 360.0)
        mask = ds['ASPECT'].where(ds['ASPECT']<=180.0)
        aspect = ds['ASPECT'].values
        aspect[aspect<180] = aspect[aspect<180]*-1.0
        aspect[aspect>=180] = 360.0 - aspect[aspect>=180]
        #ds['ASPECT'] = (('south_north','west_east'),aspect)
        ds['ASPECT'] = aspect
        
        # Auxiliary variables
        mask = ds.MASK.values
        slope = ds.SLOPE.values
        aspect = ds.ASPECT.values
    else:
        # Auxiliary variables
        mask = 1 
        slope = 0
        aspect = 0


    #-----------------------------------
    # Check bounds for relative humidity 
    #-----------------------------------
    RH2[RH2 > 100.0] = 100.0
    RH2[RH2 < 0.0] = 0.1

    #-----------------------------------
    # Add variables to file 
    #-----------------------------------
    add_variable_along_point(dso, hgt, 'HGT', 'm', 'Elevation')
    add_variable_along_point(dso, aspect, 'ASPECT', 'degrees', 'Aspect of slope')
    add_variable_along_point(dso, slope, 'SLOPE', 'degrees', 'Terrain slope')
    add_variable_along_point(dso, mask, 'MASK', 'boolean', 'Glacier mask')
    add_variable_along_timelatlon_point(dso, T2, 'T2', 'K', 'Temperature at 2 m')
    add_variable_along_timelatlon_point(dso, RH2, 'RH2', '%', 'Relative humidity at 2 m')
    add_variable_along_timelatlon_point(dso, U2, 'U2', 'm s\u207b\xb9', 'Wind velocity at 2 m')
    add_variable_along_timelatlon_point(dso, G, 'G', 'W m\u207b\xb2', 'Incoming shortwave radiation')
    add_variable_along_timelatlon_point(dso, PRES, 'PRES', 'hPa', 'Atmospheric Pressure')
    
    if (RRR_var in df):
        add_variable_along_timelatlon_point(dso, RRR, 'RRR', 'mm', 'Total precipitation (liquid+solid)')
    
    if(SNOWFALL_var in df):
        add_variable_along_timelatlon_point(dso, SNOWFALL, 'SNOWFALL', 'm', 'Snowfall')

    if(LWin_var in df):
        add_variable_along_timelatlon_point(dso, LW, 'LWin', 'W m\u207b\xb2', 'Incoming longwave radiation')
    if(N_var in df):
        add_variable_along_timelatlon_point(dso, N, 'N', '%', 'Cloud cover fraction')

    #-----------------------------------
    # Write file to disc 
    #-----------------------------------
    dso.to_netcdf(cosipy_file)


    print('Input file created \n')
    print('-------------------------------------------')

   
    #-----------------------------------
    # Do some checks
    #-----------------------------------
    check(dso.T2,316.16,223.16)
    check(dso.RH2,100.0,0.0)
    check(dso.U2, 50.0, 0.0)
    check(dso.RRR,20.0,0.0)
    check(dso.G,1600.0,0.0)
    check(dso.PRES,1080.0,200.0)




def create_2D_input(cs_file, cosipy_file, static_file, start_date, end_date, x0=None, x1=None, y0=None, y1=None):
    """ This function creates an input dataset from an offered csv file with input point data
        Here you need to define how to interpolate the data.

        Please note, there should be only one header line in the file.

        Latest update: 
            Tobias Sauter 07.07.2019
    """

    print('-------------------------------------------')
    print('Create input \n')
    print('Read input file %s' % (cs_file))

    #-----------------------------------
    # Read data
    #-----------------------------------
    date_parser = lambda x: dateutil.parser.parse(x, ignoretz=True)
    df = pd.read_csv(cs_file, 
        delimiter='\t', index_col=['TIMESTAMP'], parse_dates=['TIMESTAMP'], 
        na_values='NAN',date_parser=date_parser)

    #-----------------------------------
    # Select time slice
    #-----------------------------------
    if ((start_date != None) & (end_date !=None)): 
        df = df.loc[start_date:end_date]

    #-----------------------------------
    # Load static data
    #-----------------------------------
    print('Read static file %s \n' % (static_file))
    ds = xr.open_dataset(static_file)
    
    #-----------------------------------
    # Create subset
    #-----------------------------------
    print(ds)
    ds = ds.sel(south_north=slice(y0,y1), west_east=slice(x0,x1))
    print(ds)

    dso = xr.Dataset()

    x, y = np.meshgrid(ds.west_east, ds.south_north)
    dso.coords['time'] = (('time'), df.index.values)
    dso.coords['lat'] = (('south_north','west_east'), y)
    dso.coords['lon'] = (('south_north','west_east'), x)

    #-----------------------------------
    # Order variables
    #-----------------------------------
    df[T2_var] = df[T2_var].apply(pd.to_numeric, errors='coerce')
    df[RH2_var] = df[RH2_var].apply(pd.to_numeric, errors='coerce')
    df[U2_var] = df[U2_var].apply(pd.to_numeric, errors='coerce')
    df[G_var] = df[G_var].apply(pd.to_numeric, errors='coerce')
    df[PRES_var] = df[PRES_var].apply(pd.to_numeric, errors='coerce')
    
    if (RRR_var in df):
        df[RRR_var] = df[RRR_var].apply(pd.to_numeric, errors='coerce')

    if (PRES_var not in df):
        df[PRES_var] = 660.00

    if (LWin_var not in df and N_var not in df):
        print("ERROR no longwave incoming or cloud cover data")
        sys.exit()
    elif (LWin_var in df):
        df[LWin_var] = df[LWin_var].apply(pd.to_numeric, errors='coerce')
    elif (N_var in df):
        df[N_var] = df[N_var].apply(pd.to_numeric, errors='coerce')

    if (SNOWFALL_var in df):
        df[SNOWFALL_var] = df[SNOWFALL_var].apply(pd.to_numeric, errors='coerce')

    #-----------------------------------
    # Get values from file
    #-----------------------------------
    T2 = df[T2_var]         # Temperature
    RH2 = df[RH2_var]       # Relative humdity
    U2 = df[U2_var]         # Wind velocity
    G = df[G_var]           # Incoming shortwave radiation
    PRES = df[PRES_var]     # Pressure

    #-----------------------------------
    # Create numpy arrays for the 2D fields
    #-----------------------------------
    T_interp = np.zeros([len(dso.time), len(ds.south_north), len(ds.west_east)])
    RH_interp = np.zeros([len(dso.time), len(ds.south_north), len(ds.west_east)])
    U_interp = np.zeros([len(dso.time), len(ds.south_north), len(ds.west_east)])
    G_interp = np.zeros([len(dso.time), len(ds.south_north), len(ds.west_east)])
    P_interp = np.zeros([len(dso.time), len(ds.south_north), len(ds.west_east)])
    LWin_interp = np.zeros([len(dso.time), len(ds.south_north), len(ds.west_east)])
    N_interp = np.zeros([len(dso.time), len(ds.south_north), len(ds.west_east)])
    
    if (RRR_var in df):
        RRR = df[RRR_var]       # Precipitation
        RRR_interp = np.zeros([len(dso.time), len(ds.south_north), len(ds.west_east)])

    if(SNOWFALL_var in df):
        SNOWFALL = df[SNOWFALL_var]      # Incoming longwave radiation
        SNOWFALL_interp = np.zeros([len(dso.time), len(ds.south_north), len(ds.west_east)])

    if(LWin_var in df):
        LW = df[LWin_var]      # Incoming longwave radiation
        LW_interp = np.zeros([len(dso.time), len(ds.south_north), len(ds.west_east)])

    if(N_var in df):
        N = df[N_var]        # Cloud cover fraction
        N_interp = np.zeros([len(dso.time), len(ds.south_north), len(ds.west_east)])

    #-----------------------------------
    # Interpolate point data to grid 
    #-----------------------------------
    print('Interpolate CR file to grid')
   
    # Interpolate data (T, RH, RRR, U)  to grid using lapse rates
    for t in range(len(dso.time)):
        T_interp[t,:,:] = (T2[t]) + (ds.HGT.values-stationAlt)*lapse_T
        RH_interp[t,:,:] = RH2[t] + (ds.HGT.values-stationAlt)*lapse_RH
        U_interp[t,:,:] = U2[t]

        # Interpolate pressure using the barometric equation
        SLP = PRES[t]/np.power((1-(0.0065*stationAlt)/(288.15)), 5.255)
        P_interp[t,:,:] = SLP * np.power((1-(0.0065*ds.HGT.values)/(288.15)), 5.255)

        if (RRR_var in df):
            RRR_interp[t,:,:] = np.maximum(RRR[t] + (ds.HGT.values-stationAlt)*lapse_RRR, 0.0)
        
        if (SNOWFALL_var in df):
            SNOWFALL_interp[t, :, :] = SNOWFALL[t] + (ds.HGT.values-stationAlt)*lapse_SNOWFALL

        if(LWin_var in df):
            LW_interp[t,:,:] = LW[t]
        
        if(N_var in df):
            N_interp[t,:,:] = N[t]

    # Change aspect to south==0, east==negative, west==positive
    ds['ASPECT'] = np.mod(ds['ASPECT']+180.0, 360.0)
    mask = ds['ASPECT'].where(ds['ASPECT']<=180.0)
    aspect = ds['ASPECT'].values
    aspect[aspect<180] = aspect[aspect<180]*-1.0
    aspect[aspect>=180] = 360.0 - aspect[aspect>=180]
    ds['ASPECT'] = (('south_north','west_east'),aspect)
    print(('Number of glacier cells: %i') % (np.count_nonzero(~np.isnan(ds['MASK'].values))))
    print(('Number of glacier cells: %i') % (np.nansum(ds['MASK'].values)))

    # Auxiliary variables
    mask = ds.MASK.values
    slope = ds.SLOPE.values
    aspect = ds.ASPECT.values
    south_norths = ds.south_north.values
    west_easts = ds.west_east.values
    sw = G.values

    #-----------------------------------
    # Run radiation module 
    #-----------------------------------
    if radiationModule:
        print('Run the radiation module')
    else:
        print('No radiation module used')

    for t in range(len(dso.time)):
        doy = df.index[t].dayofyear
        hour = df.index[t].hour
        for i in range(len(ds.south_north)):
            for j in range(len(ds.west_east)):
                    if radiationModule:
                        G_interp[t,i,j] = np.maximum(0.0, correctRadiation(south_norths[i],west_easts[j], timezone_lon, doy, hour, slope[i,j], aspect[i,j], sw[t], zeni_thld))
                    else:
                        G_interp[t,i,j] = sw[t]

    #-----------------------------------
    # Check bounds for relative humidity 
    #-----------------------------------
    RH_interp[RH_interp > 100.0] = 100.0
    RH_interp[RH_interp < 0.0] = 0.1

    #-----------------------------------
    # Add variables to file 
    #-----------------------------------
    add_variable_along_latlon(dso, ds.HGT.values, 'HGT', 'm', 'Elevation')
    add_variable_along_latlon(dso, ds.ASPECT.values, 'ASPECT', 'degrees', 'Aspect of slope')
    add_variable_along_latlon(dso, ds.SLOPE.values, 'SLOPE', 'degrees', 'Terrain slope')
    add_variable_along_latlon(dso, ds.MASK.values, 'MASK', 'boolean', 'Glacier mask')
    add_variable_along_timelatlon(dso, T_interp, 'T2', 'K', 'Temperature at 2 m')
    add_variable_along_timelatlon(dso, RH_interp, 'RH2', '%', 'Relative humidity at 2 m')
    add_variable_along_timelatlon(dso, U_interp, 'U2', 'm s\u207b\xb9', 'Wind velocity at 2 m')
    add_variable_along_timelatlon(dso, G_interp, 'G', 'W m\u207b\xb2', 'Incoming shortwave radiation')
    add_variable_along_timelatlon(dso, P_interp, 'PRES', 'hPa', 'Atmospheric Pressure')
    
    if (RRR_var in df):
        add_variable_along_timelatlon(dso, RRR_interp, 'RRR', 'mm', 'Total precipitation (liquid+solid)')
    
    if(SNOWFALL_var in df):
        add_variable_along_timelatlon(dso, SNOWFALL_interp, 'SNOWFALL', 'm', 'Snowfall')

    if(LWin_var in df):
        add_variable_along_timelatlon(dso, LW_interp, 'LWin', 'W m\u207b\xb2', 'Incoming longwave radiation')
    if(N_var in df):
        add_variable_along_timelatlon(dso, N_interp, 'N', '%', 'Cloud cover fraction')

    encoding = dict()
    for var in IO.get_result().data_vars:
        dataMin = IO.get_result()[var].min(skipna=True).values
        dataMax = IO.get_result()[var].max(skipna=True).values
        
        dtype = 'int16'
        FillValue = -9999
        scale_factor, add_offset = compute_scale_and_offset(dataMin, dataMax, 16)
        encoding[var] = dict(zlib=True, complevel=2, dtype=dtype, scale_factor=scale_factor, add_offset=add_offset, _FillValue=FillValue)

    #-----------------------------------
    # Write file to disc 
    #-----------------------------------
    dso.to_netcdf(cosipy_file, encoding=encoding)


    print('Input file created \n')
    print('-------------------------------------------')

   
    #-----------------------------------
    # Do some checks
    #-----------------------------------
    check(dso.T2,316.16,223.16)
    check(dso.RH2,100.0,0.0)
    check(dso.U2, 50.0, 0.0)
    check(dso.RRR,20.0,0.0)
    check(dso.G,1600.0,0.0)
    check(dso.PRES,1080.0,200.0)

    if(SNOWFALL_var in df):
        check(ds.SNOWFALL,0.1,0.0)

def add_variable_along_timelatlon(ds, var, name, units, long_name):
    """ This function adds missing variables to the DATA class """
    ds[name] = (('time','south_north','west_east'), var)
    ds[name].attrs['units'] = units
    ds[name].attrs['long_name'] = long_name
    return ds

def add_variable_along_latlon(ds, var, name, units, long_name):
    """ This function self.adds missing variables to the self.DATA class """
    ds[name] = (('south_north','west_east'), var)
    ds[name].attrs['units'] = units
    ds[name].attrs['long_name'] = long_name
    ds[name].encoding['_FillValue'] = -9999
    return ds

def add_variable_along_timelatlon_point(ds, var, name, units, long_name):
    """ This function adds missing variables to the DATA class """
    ds[name] = (('time','south_north','west_east'), np.reshape(var,(len(var),1,1)))
    ds[name].attrs['units'] = units
    ds[name].attrs['long_name'] = long_name
    return ds

def add_variable_along_point(ds, var, name, units, long_name):
    """ This function adds missing variables to the DATA class """
    ds[name] = (('south_north','west_east'), np.reshape(var,(1,1)))
    ds[name].attrs['units'] = units
    ds[name].attrs['long_name'] = long_name
    return ds

def check(field, max, min):
    '''Check the validity of the input data '''
    if np.nanmax(field) > max or np.nanmin(field) < min:
        print('\n\nWARNING! Please check the data, its seems they are out of a reasonalbe range %s MAX: %.2f MIN: %.2f \n' % (str.capitalize(field.name), np.nanmax(field), np.nanmin(field)))
     
    if np.isnan((np.min(field.values))):
        print('ERROR this does not work! %s VALUE: %.2f \n' % (str.capitalize(field.name), np.min(field.values)))

def compute_scale_and_offset(min, max, n):
    # stretch/compress data to the available packed range
    scale_factor = (max - min) / (2 ** n - 1)
    # translate the range to be symmetric about zero
    add_offset = min + 2 ** (n - 1) * scale_factor
    return (scale_factor, add_offset)


if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description='Create 2D input file from csv file.')
    parser.add_argument('-c', '-csv_file', dest='csv_file', help='Csv file(see readme for file convention)')
    parser.add_argument('-o', '-cosipy_file', dest='cosipy_file', help='Name of the resulting COSIPY file')
    parser.add_argument('-s', '-static_file', dest='static_file', help='Static file containing DEM, Slope etc.')
    parser.add_argument('-b', '-start_date', dest='start_date', help='Start date')
    parser.add_argument('-e', '-end_date', dest='end_date', help='End date')
    parser.add_argument('-xl', '-xl', dest='xl', type=float, const=None, help='left longitude value of the subset')
    parser.add_argument('-xr', '-xr', dest='xr', type=float, const=None, help='right longitude value of the subset')
    parser.add_argument('-yl', '-yl', dest='yl', type=float, const=None, help='lower latitude value of the subset')
    parser.add_argument('-yu', '-yu', dest='yu', type=float, const=None, help='upper latitude value of the subset')

    args = parser.parse_args()
    if point_model:
        create_1D_input(args.csv_file, args.cosipy_file, args.static_file, args.start_date, args.end_date) 
    else:
        create_2D_input(args.csv_file, args.cosipy_file, args.static_file, args.start_date, args.end_date, args.xl, args.xr, args.yl, args.yu) 
