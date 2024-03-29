"""
 This file reads the input data (model forcing) and write the output to netcdf file
"""

import os
import sys
import xarray as xr
import pandas as pd
import numpy as np
import time
import logging
from modules.radCor import correctRadiation
from constants import *
from config import * 
import configparser

class IOClass:

    def __init__(self, DATA=None):
        """ Init IO Class"""

        # start module logging
        self.logger = logging.getLogger(__name__)
        
        # Read variable list from file
        config = configparser.ConfigParser()
        config.read('output')
        self.atm = config['vars']['atm']
        self.internal = config['vars']['internal']
        self.full = config['vars']['full']

        # Initialize data
        self.DATA = DATA
        self.RESTART = None
        self.RESULT = None
      
        # If local IO class is initialized we need to get the dimensions of the dataset
        if DATA is not None:
            self.time = self.DATA.dims['time']

    #==============================================================================
    # Creates the input data and reads the restart file, if necessary. The function
    # returns the DATA xarray dataset which contains all input variables.
    #==============================================================================
    def create_data_file(self):
        """ Returns the DATA xarray dataset"""
    
        if (restart==True):
            print('--------------------------------------------------------------')
            print('\t RESTART FROM PREVIOUS STATE')
            print('-------------------------------------------------------------- \n')
            
            # Load the restart file
            timestamp = pd.to_datetime(time_start).strftime('%Y-%m-%dT%H-%M-%S')
            if (os.path.isfile(os.path.join(data_path, 'restart', 'restart_'+timestamp+'.nc')) & (time_start != time_end)):
                self.GRID_RESTART = xr.open_dataset(os.path.join(data_path, 'restart', 'restart_'+timestamp+'.nc'))
                self.restart_date = self.GRID_RESTART.time     # Get time of the last calculation
                self.init_data_dataset()                       # Read data from the last date to the end of the data file
            else:
                self.logger.error('No restart file available for the given date %s' % (timestamp))  # if there is a problem kill the program
                self.logger.error('OR start date %s equals end date %s \n' % (time_start, time_end))
                sys.exit(1)
        else:
            self.restart_date = None
            self.init_data_dataset()  # If no restart, read data according to the dates defined in the config.py

        #----------------------------------------------
        # Tile the data is desired
        #----------------------------------------------
        if tile:
            self.DATA = self.DATA.isel(south_north=slice(ystart,yend), west_east=slice(xstart,xend))
        
        self.ny = self.DATA.dims['south_north']
        self.nx = self.DATA.dims['west_east']
        self.time = self.DATA.dims['time']
        
        return self.DATA


   
    #==============================================================================
    # The functions create_result_file, create_restart_file, and create_grid_restart
    # are three which create and return the following structures:
    #
    #   create_result_file  :: Creates and initializes the RESULT xarray dataset
    #   create_restart_file :: Creates and initializes the RESTART xarray dataset
    #   create_grid_restart :: Creates and initializes the GRID structure which 
    #                          contains the layer state of the last time step. The
    #                          last state is required for the restart option
    #==============================================================================
    #----------------------------------------------
    # Creates the result xarray dataset
    #----------------------------------------------
    def create_result_file(self):
        """ Returns the data xarray """
        self.init_result_dataset()
        return self.RESULT
         
    #----------------------------------------------
    # Creates the restart xarray dataset
    #----------------------------------------------
    def create_restart_file(self):
        """ Returns the data xarray """
        self.init_restart_dataset()
        return self.RESTART

    #----------------------------------------------
    # Returns the restart dataset 
    #----------------------------------------------
    def create_grid_restart(self):
        return self.GRID_RESTART


    #==============================================================================
    # The init_data_dataset read the input NetCDF dataset and stores the data in
    # an xarray. 
    #==============================================================================
    #----------------------------------------------
    # Reads the input data into a xarray dataset 
    #----------------------------------------------
    def init_data_dataset(self):
        """     
        PRES        ::   Air Pressure [hPa]
        N           ::   Cloud cover  [fraction][%/100]
        RH2         ::   Relative humidity (2m over ground)[%]
        RRR         ::   Precipitation per time step [mm]
        SNOWFALL    ::   Snowfall per time step [m]
        G           ::   Solar radiation at each time step [W m-2]
        T2          ::   Air temperature (2m over ground) [K]
        U2          ::   Wind speed (magnitude) [m/s]
        HGT         ::   Elevation [m]
        """
    
        # Open input dataset
        self.DATA = xr.open_dataset(os.path.join(data_path,'input',input_netcdf))
        self.DATA['time'] = np.sort(self.DATA['time'].values)
        start_interval=str(self.DATA.time.values[0])[0:16]
        end_interval = str(self.DATA.time.values[-1])[0:16]
        time_steps = str(self.DATA.dims['time'])
        print('\n Maximum available time interval from %s until %s. Time steps: %s \n\n' % (start_interval, end_interval, time_steps))

        # Check if restart option is set
        if self.restart_date is None:
            print('--------------------------------------------------------------')
            print('\t Integration from %s to %s' % (time_start, time_end))
            print('--------------------------------------------------------------\n')
            self.DATA = self.DATA.sel(time=slice(time_start, time_end))   # Select dates from config.py
        else:
            # There is nothing to do if the dates are equal
            if (self.restart_date==time_end):
                print('Start date equals end date ... no new data ... EXIT')
                sys.exit(1)
            else:
                # otherwise, run the model from the restart date to the defined end date
                print('Starting from %s (from restart file) to %s (from config.py) \n' % (self.restart_date.values, time_end))
                self.DATA = self.DATA.sel(time=slice(self.restart_date, time_end))

        if time_start < start_interval:
            print('\n WARNING! Selected startpoint before first timestep of input data\n')
        if time_end > end_interval:
            print('\n WARNING! Selected endpoint after last timestep of input data\n')
        if time_start > end_interval or time_end < start_interval:
            print('\n ERROR! Selected period not availalbe in input data\n')


        print('--------------------------------------------------------------')
        print('Checking input data .... \n')
        
        # Define a auxiliary function to check the validity of the data
        def check(field, max, min):
            '''Check the validity of the input data '''
            if np.nanmax(field) > max or np.nanmin(field) < min:
                print('Please check the input data, its seems they are out of range %s MAX: %.2f MIN: %.2f \n' % (str.capitalize(field.name), np.nanmax(field), np.nanmin(field)))
        # Check if data is within valid bounds
        if ('T2' in self.DATA):
            print('Temperature data (T2) ... ok ')
            check(self.DATA.T2, 313.16, 243.16)
        if ('RH2' in self.DATA):
            print('Relative humidity data (RH2) ... ok ')
            check(self.DATA.RH2, 100.0, 0.0)
        if ('G' in self.DATA):
            print('Shortwave data (G) ... ok ')
            check(self.DATA.G, 1600.0, 0.0)
        if ('U2' in self.DATA):
            print('Wind velocity data (U2) ... ok ')
            check(self.DATA.U2, 50.0, 0.0)
        if ('RRR' in self.DATA):
            print('Precipitation data (RRR) ... ok ')
            check(self.DATA.RRR, 20.0, 0.0)
        if ('N' in self.DATA):
            print('Cloud cover data (N) ... ok ')
            check(self.DATA.N, 1.0, 0.0)
        if ('PRES' in self.DATA):
            print('Pressure data (PRES) ... ok ')
            check(self.DATA.PRES, 1080.0, 400.0)
        if ('LWin' in self.DATA):
            print('Incoming longwave data (LWin) ... ok ')
            check(self.DATA.LWin, 400.0, 200.0)
        if ('SNOWFALL' in self.DATA):
            print('Snowfall data (SNOWFALL) ... ok ')
            check(self.DATA.SNOWFALL, 0.1, 0.0)

        print('\n Glacier gridpoints: %s \n\n' %(np.nansum(self.DATA.MASK>=1)))

 
    #==============================================================================
    # The init_result_datasets creates the final dataset which stores the results
    # from the individual cosipy runs. After the dataset has been filled with the
    # runs from all workers the dataset is written to disc.
    #==============================================================================
    #----------------------------------------------
    # Initializes the result xarray dataset
    #----------------------------------------------
    def init_result_dataset(self):
        """ This function creates the result file 
        Args:
            
            self.DATA    ::  self.DATA structure 
            
        Returns:
            
            self.RESULT  ::  one-dimensional self.RESULT structure"""
        
        # Coordinates
        self.RESULT = xr.Dataset()
        self.RESULT.coords['time'] = self.DATA.coords['time']
        self.RESULT.coords['lat'] = self.DATA.coords['lat']
        self.RESULT.coords['lon'] = self.DATA.coords['lon']

        # Attributes
        self.RESULT.attrs['Remesh_method'] = remesh_method
        self.RESULT.attrs['Start_from_restart_file'] = str(restart)
        self.RESULT.attrs['Force_use_TP'] = str(force_use_TP)
        self.RESULT.attrs['Time_step_input_file_seconds'] = dt
        self.RESULT.attrs['Density_threshold_merging'] = density_threshold_merging
        self.RESULT.attrs['Temperature_threshold_merging'] = temperature_threshold_merging
        self.RESULT.attrs['Merge_max'] = merge_max

        self.RESULT.attrs['Albedo_method'] = albedo_method
        self.RESULT.attrs['Densification_method'] = densification_method
        self.RESULT.attrs['Penetrating_method'] = penetrating_method
        self.RESULT.attrs['Roughness_method'] = roughness_method
        self.RESULT.attrs['Saturation_water_vapour_method'] = saturation_water_vapour_method
        self.RESULT.attrs['Initial_snowheight'] = initial_snowheight_constant
        self.RESULT.attrs['Initial_snow_layer_heights'] = initial_snow_layer_heights
        self.RESULT.attrs['Initial_glacier_layer_heights'] = initial_glacier_layer_heights
        self.RESULT.attrs['Initial_glacier_height'] = initial_glacier_height
        self.RESULT.attrs['Initial_top_density_snowpack'] = initial_top_density_snowpack
        self.RESULT.attrs['Initial_botton_density_snowpack'] = initial_botton_density_snowpack
        self.RESULT.attrs['Temperature_top'] = temperature_top_constant
        self.RESULT.attrs['Temperature_bottom'] = temperature_bottom
        self.RESULT.attrs['Const_init_temp'] = const_init_temp
        self.RESULT.attrs['First_layer_height_log_profile'] = first_layer_height
        self.RESULT.attrs['Layer_stretching_log_profile'] = layer_stretching
        self.RESULT.attrs['Minimum_snow_to_reset_albedo'] = minimum_snow_to_reset_albedo
        self.RESULT.attrs['Albedo_fresh_snow'] = albedo_fresh_snow
        self.RESULT.attrs['Albedo_firn'] = albedo_firn
        self.RESULT.attrs['Albedo_ice'] = albedo_ice
        self.RESULT.attrs['Albedo_mod_snow_aging'] = albedo_mod_snow_aging
        self.RESULT.attrs['Albedo_mod_snow_depth'] = albedo_mod_snow_depth
        self.RESULT.attrs['Roughness_fresh_snow'] = roughness_fresh_snow
        self.RESULT.attrs['Roughness_ice'] = roughness_ice
        self.RESULT.attrs['Roughness_firn'] = roughness_firn
        self.RESULT.attrs['Aging_factor_roughness'] = aging_factor_roughness
        self.RESULT.attrs['Surface_emission_coeff'] = surface_emission_coeff
        self.RESULT.attrs['Snow_ice_threshold'] = snow_ice_threshold
        self.RESULT.attrs['Snow_firn_threshold'] = snow_firn_threshold
        self.RESULT.attrs['Center_snow_transfer_function'] = center_snow_transfer_function
        self.RESULT.attrs['Spread_snow_transfer_function'] = spread_snow_transfer_function

        # Variables given by the input dataset
        self.add_variable_along_latlon(self.RESULT, self.DATA.HGT, 'HGT', 'm', 'Elevation')
        self.add_variable_along_latlon(self.RESULT, self.DATA.MASK, 'MASK', 'boolean', 'Glacier mask')
        self.add_variable_along_latlontime(self.RESULT, self.DATA.T2, 'T2', 'K', 'Air temperature at 2 m')
        self.add_variable_along_latlontime(self.RESULT, self.DATA.RH2, 'RH2', '%', 'Relative humidity at 2 m')
        self.add_variable_along_latlontime(self.RESULT, self.DATA.U2, 'U2', 'm s\u207b\xb9', 'Wind velocity at 2 m')
        self.add_variable_along_latlontime(self.RESULT, self.DATA.PRES, 'PRES', 'hPa', 'Atmospheric pressure')
        self.add_variable_along_latlontime(self.RESULT, self.DATA.G, 'G', 'W m\u207b\xb2', 'Incoming shortwave radiation')
        
        if ('RRR' in self.DATA):
            self.add_variable_along_latlontime(self.RESULT, self.DATA.RRR, 'RRR', 'mm','Total precipiation')
        else:
            self.add_variable_along_latlontime(self.RESULT, np.full_like(self.DATA.T2, np.nan), 'RRR', 'mm','Total precipiation')
        
        if ('SNOWFALL' in self.DATA):
            self.add_variable_along_latlontime(self.RESULT, self.DATA.SNOWFALL, 'SNOWFALL', 'm', 'Snowfall')
       
        if ('N' in self.DATA):
            self.add_variable_along_latlontime(self.RESULT, self.DATA.N, 'N', '-', 'Cloud fraction')
        else:
            self.add_variable_along_latlontime(self.RESULT, np.full_like(self.DATA.T2, np.nan), 'N', '-', 'Cloud fraction')
        
        if ('LWin' in self.DATA):
            self.add_variable_along_latlontime(self.RESULT, self.DATA.LWin, 'LWin', 'W m\u207b\xb2', 'Incoming longwave radiation')
        
        print('\n') 
        print('Output dataset ... ok')
        return self.RESULT
  

    #==============================================================================
    # This function creates the global numpy arrays which store the variables.
    # The global array is filled with the local results from the workers. Finally,
    # the arrays are assigned to the RESULT dataset and is stored to disc (see COSIPY.py)
    #==============================================================================
    def create_global_result_arrays(self):

        if ('RAIN' in self.atm):
            self.RAIN = np.full((self.time,self.ny,self.nx), np.nan)
        if ('SNOWFALL' in self.atm):
            self.SNOWFALL = np.full((self.time,self.ny,self.nx), np.nan)
        if ('LWin' in self.atm):
            self.LWin = np.full((self.time,self.ny,self.nx), np.nan)
        if ('LWout' in self.atm):
            self.LWout = np.full((self.time,self.ny,self.nx), np.nan)
        if ('H' in self.atm):
            self.H = np.full((self.time,self.ny,self.nx), np.nan)
        if ('LE' in self.atm):
            self.LE = np.full((self.time,self.ny,self.nx), np.nan)
        if ('B' in self.atm):
            self.B = np.full((self.time,self.ny,self.nx), np.nan)
        if ('MB' in self.internal):
            self.MB = np.full((self.time,self.ny,self.nx), np.nan)
        if ('surfMB' in self.internal):
            self.surfMB = np.full((self.time,self.ny,self.nx), np.nan)
        if ('Q' in self.internal):
            self.Q = np.full((self.time,self.ny,self.nx), np.nan)
        if ('SNOWHEIGHT' in self.internal):
            self.SNOWHEIGHT = np.full((self.time,self.ny,self.nx), np.nan)
        if ('TOTALHEIGHT' in self.internal):
            self.TOTALHEIGHT = np.full((self.time,self.ny,self.nx), np.nan)
        if ('TS' in self.atm):
            self.TS = np.full((self.time,self.ny,self.nx), np.nan)
        if ('ALBEDO' in self.atm):
            self.ALBEDO = np.full((self.time,self.ny,self.nx), np.nan)
        if ('NLAYERS' in self.internal):
            self.NLAYERS = np.full((self.time,self.ny,self.nx), np.nan)
        if ('ME' in self.internal):
            self.ME = np.full((self.time,self.ny,self.nx), np.nan)
        if ('intMB' in self.internal):
            self.intMB = np.full((self.time,self.ny,self.nx), np.nan)
        if ('EVAPORATION' in self.internal):
            self.EVAPORATION = np.full((self.time,self.ny,self.nx), np.nan)
        if ('SUBLIMATION' in self.internal):
            self.SUBLIMATION = np.full((self.time,self.ny,self.nx), np.nan)
        if ('CONDENSATION' in self.internal):
            self.CONDENSATION = np.full((self.time,self.ny,self.nx), np.nan)
        if ('DEPOSITION' in self.internal):
            self.DEPOSITION = np.full((self.time,self.ny,self.nx), np.nan)
        if ('REFREEZE' in self.internal):
            self.REFREEZE = np.full((self.time,self.ny,self.nx), np.nan)
        if ('subM' in self.internal):
            self.subM = np.full((self.time,self.ny,self.nx), np.nan)
        if ('Z0' in self.atm):
            self.Z0 = np.full((self.time,self.ny,self.nx), np.nan)
        if ('surfM' in self.internal):
            self.surfM= np.full((self.time,self.ny,self.nx), np.nan)

        if full_field:
            if ('HEIGHT' in self.full):
                self.LAYER_HEIGHT = np.full((self.time,self.ny,self.nx,max_layers), np.nan)
            if ('RHO' in self.full):
                self.LAYER_RHO = np.full((self.time,self.ny,self.nx,max_layers), np.nan)
            if ('T' in self.full):
                self.LAYER_T = np.full((self.time,self.ny,self.nx,max_layers), np.nan)
            if ('LWC' in self.full):
                self.LAYER_LWC = np.full((self.time,self.ny,self.nx,max_layers), np.nan)
            if ('CC' in self.full):
                self.LAYER_CC = np.full((self.time,self.ny,self.nx,max_layers), np.nan)
            if ('POROSITY' in self.full):
                self.LAYER_POROSITY = np.full((self.time,self.ny,self.nx,max_layers), np.nan)
            if ('ICE_FRACTION' in self.full):
                self.LAYER_ICE_FRACTION = np.full((self.time,self.ny,self.nx,max_layers), np.nan)
            if ('IRREDUCIBLE_WATER' in self.full):
                self.LAYER_IRREDUCIBLE_WATER = np.full((self.time,self.ny,self.nx,max_layers), np.nan)
            if ('REFREEZE' in self.full):
                self.LAYER_REFREEZE = np.full((self.time,self.ny,self.nx,max_layers), np.nan)
   

    #==============================================================================
    # This function assigns the local results from the workers to the global
    # numpy arrays. The y and x values are the lat/lon indices.
    #==============================================================================
    def copy_local_to_global(self,y,x,local_RAIN,local_SNOWFALL,local_LWin,local_LWout,local_H,local_LE,local_B,local_MB, \
                             local_surfMB,local_Q,local_SNOWHEIGHT,local_TOTALHEIGHT,local_TS,local_ALBEDO, \
                             local_NLAYERS,local_ME,local_intMB,local_EVAPORATION,local_SUBLIMATION,local_CONDENSATION, \
                             local_DEPOSITION,local_REFREEZE,local_subM,local_Z0,local_surfM,local_LAYER_HEIGHT,local_LAYER_RHO, \
                             local_LAYER_T,local_LAYER_LWC,local_LAYER_CC,local_LAYER_POROSITY,local_LAYER_ICE_FRACTION, \
                             local_LAYER_IRREDUCIBLE_WATER,local_LAYER_REFREEZE):

        if ('RAIN' in self.atm):
            self.RAIN[:,y,x] = local_RAIN
        if ('SNOWFALL' in self.atm):
            self.SNOWFALL[:,y,x] = local_SNOWFALL
        if ('LWin' in self.atm):
            self.LWin[:,y,x] = local_LWin
        if ('LWout' in self.atm):
            self.LWout[:,y,x] = local_LWout
        if ('H' in self.atm):
            self.H[:,y,x] = local_H
        if ('LE' in self.atm):
            self.LE[:,y,x] = local_LE
        if ('B' in self.atm):
            self.B[:,y,x] = local_B
        if ('surfMB' in self.internal):
            self.surfMB[:,y,x] = local_surfMB
        if ('MB' in self.internal):
            self.MB[:,y,x] = local_MB
        if ('Q' in self.internal):
            self.Q[:,y,x] = local_Q
        if ('SNOWHEIGHT' in self.internal):
            self.SNOWHEIGHT[:,y,x] = local_SNOWHEIGHT
        if ('TOTALHEIGHT' in self.internal):
            self.TOTALHEIGHT[:,y,x] = local_TOTALHEIGHT 
        if ('TS' in self.atm):
            self.TS[:,y,x] = local_TS 
        if ('ALBEDO' in self.atm):
            self.ALBEDO[:,y,x] = local_ALBEDO 
        if ('NLAYERS' in self.internal):
            self.NLAYERS[:,y,x] = local_NLAYERS 
        if ('ME' in self.internal):
            self.ME[:,y,x] = local_ME 
        if ('intMB' in self.internal):
            self.intMB[:,y,x] = local_intMB 
        if ('EVAPORATION' in self.internal):
            self.EVAPORATION[:,y,x] = local_EVAPORATION 
        if ('SUBLIMATION' in self.internal):
            self.SUBLIMATION[:,y,x] = local_SUBLIMATION 
        if ('CONDENSATION' in self.internal):
            self.CONDENSATION[:,y,x] = local_CONDENSATION 
        if ('DEPOSITION' in self.internal):
            self.DEPOSITION[:,y,x] = local_DEPOSITION 
        if ('REFREEZE' in self.internal):
            self.REFREEZE[:,y,x] = local_REFREEZE 
        if ('subM' in self.internal):
            self.subM[:,y,x] = local_subM 
        if ('Z0' in self.atm):
            self.Z0[:,y,x] = local_Z0 
        if ('surfM' in self.internal):
            self.surfM[:,y,x] = local_surfM 

        if full_field:
            if ('HEIGHT' in self.full):
                self.LAYER_HEIGHT[:,y,x,:] = local_LAYER_HEIGHT 
            if ('RHO' in self.full):
                self.LAYER_RHO[:,y,x,:] = local_LAYER_RHO 
            if ('T' in self.full):
                self.LAYER_T[:,y,x,:] = local_LAYER_T 
            if ('LWC' in self.full):
                self.LAYER_LWC[:,y,x,:] = local_LAYER_LWC 
            if ('CC' in self.full):
                self.LAYER_CC[:,y,x,:] = local_LAYER_CC 
            if ('POROSITY' in self.full):
                self.LAYER_POROSITY[:,y,x,:] = local_LAYER_POROSITY 
            if ('ICE_FRACTION' in self.full):
                self.LAYER_ICE_FRACTION[:,y,x,:] = local_LAYER_ICE_FRACTION 
            if ('IRREDUCIBLE_WATER' in self.full):
                self.LAYER_IRREDUCIBLE_WATER[:,y,x,:] = local_LAYER_IRREDUCIBLE_WATER 
            if ('REFREEZE' in self.full):
                self.LAYER_REFREEZE[:,y,x,:] = local_LAYER_REFREEZE 
        

    #==============================================================================
    # This function adds the global numpy arrays to the RESULT dataset which will
    # be written to disc.
    #==============================================================================
    def write_results_to_file(self):
        if ('RAIN' in self.atm):
            self.add_variable_along_latlontime(self.RESULT, self.RAIN, 'RAIN', 'mm', 'Liquid precipitation') 
        if ('SNOWFALL' in self.atm):
            self.add_variable_along_latlontime(self.RESULT, self.SNOWFALL, 'SNOWFALL', 'm', 'Snowfall') 
        if ('LWin' in self.atm):
            self.add_variable_along_latlontime(self.RESULT, self.LWin, 'LWin', 'W m\u207b\xb2', 'Incoming longwave radiation') 
        if ('LWout' in self.atm):
            self.add_variable_along_latlontime(self.RESULT, self.LWout, 'LWout', 'W m\u207b\xb2', 'Outgoing longwave radiation') 
        if ('H' in self.atm):
            self.add_variable_along_latlontime(self.RESULT, self.H, 'H', 'W m\u207b\xb2', 'Sensible heat flux') 
        if ('LE' in self.atm):
            self.add_variable_along_latlontime(self.RESULT, self.LE, 'LE', 'W m\u207b\xb2', 'Latent heat flux') 
        if ('B' in self.atm):
            self.add_variable_along_latlontime(self.RESULT, self.B, 'B', 'W m\u207b\xb2', 'Ground heat flux') 
        if ('surfMB' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.surfMB, 'surfMB', 'm w.e.', 'Surface mass balance') 
        if ('MB' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.MB, 'MB', 'm w.e.', 'Mass balance') 
        if ('Q' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.Q, 'Q', 'm w.e.', 'Runoff') 
        if ('SNOWHEIGHT' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.SNOWHEIGHT, 'SNOWHEIGHT', 'm', 'Snowheight') 
        if ('TOTALHEIGHT' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.TOTALHEIGHT, 'TOTALHEIGHT', 'm', 'Total domain height') 
        if ('TS' in self.atm):
            self.add_variable_along_latlontime(self.RESULT, self.TS, 'TS', 'K', 'Surface temperature') 
        if ('ALBEDO' in self.atm):
            self.add_variable_along_latlontime(self.RESULT, self.ALBEDO, 'ALBEDO', '-', 'Albedo') 
        if ('NLAYERS' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.NLAYERS, 'NLAYERS', '-', 'Number of layers') 
        if ('ME' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.ME, 'ME', 'W m\u207b\xb2', 'Available melt energy') 
        if ('intMB' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.intMB, 'intMB', 'm w.e.', 'Internal mass balance') 
        if ('EVAPORATION' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.EVAPORATION, 'EVAPORATION', 'm w.e.', 'Evaporation') 
        if ('SUBLIMATION' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.SUBLIMATION, 'SUBLIMATION', 'm w.e.', 'Sublimation') 
        if ('CONDENSATION' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.CONDENSATION, 'CONDENSATION', 'm w.e.', 'Condensation') 
        if ('DEPOSITION' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.DEPOSITION, 'DEPOSITION', 'm w.e.', 'Deposition') 
        if ('REFREEZE' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.REFREEZE, 'REFREEZE', 'm w.e.', 'Refreezing') 
        if ('subM' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.subM, 'subM', 'm w.e.', 'Subsurface melt') 
        if ('Z0' in self.atm):
            self.add_variable_along_latlontime(self.RESULT, self.Z0, 'Z0', 'm', 'Roughness length') 
        if ('surfM' in self.internal):
            self.add_variable_along_latlontime(self.RESULT, self.surfM, 'surfM', 'm w.e.', 'Surface melt') 
        
        if full_field:
            if ('HEIGHT' in self.full):
                self.add_variable_along_latlonlayertime(self.RESULT, self.LAYER_HEIGHT, 'LAYER_HEIGHT', 'm', 'Layer height') 
            if ('RHO' in self.full):
                self.add_variable_along_latlonlayertime(self.RESULT, self.LAYER_RHO, 'LAYER_RHO', 'kg m^-3', 'Layer density') 
            if ('T' in self.full):
                self.add_variable_along_latlonlayertime(self.RESULT, self.LAYER_T, 'LAYER_T', 'K', 'Layer temperature') 
            if ('LWC' in self.full):
                self.add_variable_along_latlonlayertime(self.RESULT, self.LAYER_LWC, 'LAYER_LWC', 'kg m^-2', 'Liquid water content') 
            if ('CC' in self.full):
                self.add_variable_along_latlonlayertime(self.RESULT, self.LAYER_CC, 'LAYER_CC', 'J m^-2', 'Cold content') 
            if ('POROSITY' in self.full):
                self.add_variable_along_latlonlayertime(self.RESULT, self.LAYER_POROSITY, 'LAYER_POROSITY', '-', 'Porosity') 
            if ('ICE_FRACTION' in self.full):
                self.add_variable_along_latlonlayertime(self.RESULT, self.LAYER_ICE_FRACTION, 'LAYER_ICE_FRACTION', '-', 'Ice fraction') 
            if ('IRREDUCIBLE_WATER' in self.full):
                self.add_variable_along_latlonlayertime(self.RESULT, self.LAYER_IRREDUCIBLE_WATER, 'LAYER_IRREDUCIBLE_WATER', '-', 'Irreducible water') 
            if ('REFREEZE' in self.full):
                self.add_variable_along_latlonlayertime(self.RESULT, self.LAYER_REFREEZE, 'LAYER_REFREEZE', 'm w.e.', 'Refreezing') 


    #==============================================================================
    # The init_local_result_arrays creates the local numpy arrays which store 
    # the simulations results. These arrays are returned to the main module(COSIPY.py)
    # where they are written to the RESULT xarray dataset.
    #==============================================================================
    def create_local_result_arrays(self):
        self.local_RAIN = np.full(self.time, np.nan)
        self.local_SNOWFALL = np.full(self.time, np.nan)
        self.local_LWin = np.full(self.time, np.nan)
        self.local_LWout = np.full(self.time, np.nan)
        self.local_H = np.full(self.time, np.nan)
        self.local_LE = np.full(self.time, np.nan)
        self.local_B = np.full(self.time, np.nan)
        self.local_MB = np.full(self.time, np.nan)
        self.local_surfMB = np.full(self.time, np.nan)
        self.local_Q = np.full(self.time, np.nan)
        self.local_SNOWHEIGHT = np.full(self.time, np.nan)
        self.local_TOTALHEIGHT = np.full(self.time, np.nan)
        self.local_TS = np.full(self.time, np.nan)
        self.local_ALBEDO = np.full(self.time, np.nan)
        self.local_ME = np.full(self.time, np.nan)
        self.local_intMB = np.full(self.time, np.nan)
        self.local_EVAPORATION = np.full(self.time, np.nan)
        self.local_SUBLIMATION = np.full(self.time, np.nan)
        self.local_CONDENSATION = np.full(self.time, np.nan)
        self.local_DEPOSITION = np.full(self.time, np.nan)
        self.local_REFREEZE = np.full(self.time, np.nan)
        self.local_NLAYERS = np.full(self.time, np.nan)
        self.local_subM = np.full(self.time, np.nan)
        self.local_Z0 = np.full(self.time, np.nan)
        self.local_surfM = np.full(self.time, np.nan)

        if full_field:
            self.local_LAYER_HEIGHT = np.full((self.time,max_layers), np.nan)
            self.local_LAYER_RHO = np.full((self.time,max_layers), np.nan)
            self.local_LAYER_T = np.full((self.time,max_layers), np.nan)
            self.local_LAYER_LWC = np.full((self.time,max_layers), np.nan)
            self.local_LAYER_CC = np.full((self.time,max_layers), np.nan)
            self.local_LAYER_POROSITY = np.full((self.time,max_layers), np.nan)
            self.local_LAYER_ICE_FRACTION = np.full((self.time,max_layers), np.nan)
            self.local_LAYER_IRREDUCIBLE_WATER = np.full((self.time,max_layers), np.nan)
            self.local_LAYER_REFREEZE = np.full((self.time,max_layers), np.nan)

    # TODO: Make it Pythonian - Finish the getter/setter functions
    @property
    def RAIN(self):
        return self.__RAIN
    @property
    def SNOWFALL(self):
        return self.__SNOWFALL
    @property
    def LWin(self):
        return self.__LWin
    @property
    def LWout(self):
        return self.__LWout
    @property
    def H(self):
        return self.__H
    @property
    def LE(self):
        return self.__LE
    @property
    def B(self):
        return self.__B
    @property
    def MB(self):
        return self.__MB
    
    
    @RAIN.setter
    def RAIN(self, x):
        self.__RAIN = x
    @SNOWFALL.setter
    def SNOWFALL(self, x):
        self.__SNOWFALL = x
    @LWin.setter
    def LWin(self, x):
        self.__LWin = x
    @LWout.setter
    def LWout(self, x):
        self.__LWout = x
    @H.setter
    def H(self, x):
        self.__H = x
    @LE.setter
    def LE(self, x):
        self.__LE = x
    @B.setter
    def B(self, x):
        self.__B = x
    @MB.setter
    def MB(self, x):
        self.__MB = x

    #==============================================================================
    # The next three functions initialize and write the local and global 
    # restart datasets. The init_restart_dataset creates the global xarray dataset
    # which contains the final restart variables. These variables are aggregated
    # from the local restart datasets from each worker (node). Once the variables
    # are aggregated they are written to a netcdf file (write_restart_future)
    #==============================================================================
    #----------------------------------------------
    # Initializes the restart xarray dataset
    #----------------------------------------------
    def init_restart_dataset(self):
        """ This function creates the restart file 
            
        Returns:
            
            self.RESTART  ::  xarray structure"""
        
        self.RESTART = xr.Dataset()
        self.RESTART.coords['time'] = self.DATA.coords['time'][-1]
        self.RESTART.coords['lat'] = self.DATA.coords['lat']
        self.RESTART.coords['lon'] = self.DATA.coords['lon']
        self.RESTART.coords['layer'] = np.arange(max_layers)
    
        self.add_variable_along_latlon(self.RESTART, np.full((1), np.nan), 'NLAYERS', '-', 'Number of layers')
        
        self.add_variable_along_latlonlayer(self.RESTART, np.full((self.DATA.T2.shape[1], self.DATA.T2.shape[2], self.RESTART.coords['layer'].shape[0]),
                                                            np.nan), 'LAYER_HEIGHT', 'm', 'Height of each layer')
        self.add_variable_along_latlonlayer(self.RESTART, np.full((self.DATA.T2.shape[1], self.DATA.T2.shape[2], self.RESTART.coords['layer'].shape[0]),
                                                            np.nan), 'LAYER_RHO', 'kg m^-3', 'Layer density')
        self.add_variable_along_latlonlayer(self.RESTART, np.full((self.DATA.T2.shape[1], self.DATA.T2.shape[2], self.RESTART.coords['layer'].shape[0]),
                                                            np.nan), 'LAYER_T', 'K', 'Layer temperature')
        
        print('Restart ddataset ... ok \n')
        print('--------------------------------------------------------------\n')
    
        return self.RESTART
   

    #----------------------------------------------
    # Initializes the local restart xarray dataset
    #----------------------------------------------
    def create_local_restart_dataset(self):
        """ This function creates the result dataset for a grid point 
        Args:
            
            self.DATA    ::  self.DATA structure 
            
        Returns:
            
            self.RESTART  ::  one-dimensional self.RESULT structure"""
    
        self.RESTART = xr.Dataset()
        self.RESTART.coords['time'] = self.DATA.coords['time'][-1]
        self.RESTART.coords['lat'] = self.DATA.coords['lat']
        self.RESTART.coords['lon'] = self.DATA.coords['lon']
        self.RESTART.coords['layer'] = np.arange(max_layers)
       
        self.add_variable_along_latlon(self.RESTART, np.full((1), np.nan), 'NLAYERS', '-', 'Number of layers')
        self.add_variable_along_layer(self.RESTART, np.full((self.RESTART.coords['layer'].shape[0]), np.nan), 'LAYER_HEIGHT', 'm', 'Layer height')
        self.add_variable_along_layer(self.RESTART, np.full((self.RESTART.coords['layer'].shape[0]), np.nan), 'LAYER_RHO', 'kg m^-3', 'Density of layer')
        self.add_variable_along_layer(self.RESTART, np.full((self.RESTART.coords['layer'].shape[0]), np.nan), 'LAYER_T', 'K', 'Layer temperature')
    
        return self.RESTART


    #----------------------------------------------
    # Writes the last model state (layer characgeristics) into restart dataset 
    #----------------------------------------------
    def write_restart_future(self, results, y, x):
        """ Writes the restart file 
       
        Args:
       
        results     :: RESTART xarray dataset
        y           :: y-index 
        x           :: x-index
        
        """

        self.RESTART['NLAYERS'] = results.NLAYERS.values
        self.RESTART.LAYER_HEIGHT.loc[dict(south_north=y, west_east=x, layer=np.arange(max_layers))] = results.LAYER_HEIGHT
        self.RESTART.LAYER_RHO.loc[dict(south_north=y, west_east=x, layer=np.arange(max_layers))] = results.LAYER_RHO
        self.RESTART.LAYER_T.loc[dict(south_north=y, west_east=x, layer=np.arange(max_layers))] = results.LAYER_T
    

    #==============================================================================
    # The following functions return the RESULT, RESTART and GRID structures
    #==============================================================================
    #----------------------------------------------
    # Getter/Setter functions 
    #----------------------------------------------
    def get_result(self):
        return self.RESULT

    def get_restart(self):
        return self.RESTART

    def get_grid_restart(self):
        return self.GRID_RESTART

    #==============================================================================
    # Auxiliary functions for writing variables to NetCDF files
    #==============================================================================
    def add_variable_along_latlon(self, ds, var, name, units, long_name):
        """ This function self.adds missing variables to the self.DATA class """
        ds[name] = var
        ds[name].attrs['units'] = units
        ds[name].attrs['long_name'] = long_name
        ds[name].encoding['_FillValue'] = -9999
        return ds
    
    def add_variable_along_time(self, ds, var, name, units, long_name):
        """ This function self.adds missing variables to the self.DATA class """
        ds[name] = xr.DataArray(var, coords=[('time', ds.time)])
        ds[name].attrs['units'] = units
        ds[name].attrs['long_name'] = long_name
        ds[name].encoding['_FillValue'] = -9999
        return ds
    
    def add_variable_along_latlontime(self, ds, var, name, units, long_name):
        """ This function self.adds missing variables to the self.DATA class """
        ds[name] = (('time','south_north','west_east'), var)
        ds[name].attrs['units'] = units
        ds[name].attrs['long_name'] = long_name
        ds[name].encoding['_FillValue'] = -9999
        return ds
    
    def add_variable_along_latlonlayertime(self, ds, var, name, units, long_name):
        """ This function self.adds missing variables to the self.DATA class """
        ds[name] = (('time','south_north','west_east','layer'), var)
        ds[name].attrs['units'] = units
        ds[name].attrs['long_name'] = long_name
        ds[name].encoding['_FillValue'] = -9999
        return ds
    
    def add_variable_along_latlonlayer(self, ds, var, name, units, long_name):
        """ This function self.adds missing variables to the self.DATA class """
        ds[name] = (('south_north','west_east','layer'), var)
        ds[name].attrs['units'] = units
        ds[name].attrs['long_name'] = long_name
        ds[name].encoding['_FillValue'] = -9999
        return ds
    
    def add_variable_along_layertime(self, ds, var, name, units, long_name):
        """ This function self.adds missing variables to the self.DATA class """
        ds[name] = (('time','layer'), var)
        ds[name].attrs['units'] = units
        ds[name].attrs['long_name'] = long_name
        ds[name].encoding['_FillValue'] = -9999
        return ds
    
    def add_variable_along_layer(self, ds, var, name, units, long_name):
        """ This function self.adds missing variables to the self.DATA class """
        ds[name] = (('layer'), var)
        ds[name].attrs['units'] = units
        ds[name].attrs['long_name'] = long_name
        ds[name].encoding['_FillValue'] = -9999
        return ds
