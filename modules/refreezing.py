import numpy as np
from constants import *
from config import *
import logging

def refreezing(GRID):

    # start module logging
    logger = logging.getLogger(__name__)

    # water refreezed
    water_refreezed = 0.0
    LWCref = 0.0

    # Irreducible water when refreezed
    theta_r = 0.0

    total_start = np.sum(GRID.get_liquid_water_content())

    # Loop over all internal grid points for percolation
    for idxNode in range(0, GRID.number_nodes-1, 1):

        if ((GRID.get_node_temperature(idxNode)-zero_temperature<1e-3) & (GRID.get_node_liquid_water_content(idxNode)>theta_r)):

            # Temperature difference between layer and freezing tempeature
            dT = GRID.get_node_temperature(idxNode) - zero_temperature

            # Compute conversion factor A
            A = (spec_heat_ice*ice_density)/(water_density*lat_heat_melting)

            # Changes in volumetric contents
            dtheta_w = A * dT * GRID.get_node_ice_fraction(idxNode)
            dtheta_i = (water_density/ice_density) * -dtheta_w

            # Check if enough water water to refreeze
            if ((GRID.get_node_liquid_water_content(idxNode)+dtheta_w) < theta_r):
                dtheta_w = theta_r - GRID.get_node_liquid_water_content(idxNode)
                dtheta_i = (water_density/ice_density) * -dtheta_w
                dT       = dtheta_i / A

            if ((GRID.get_node_ice_fraction(idxNode)+dtheta_i+theta_r) >= 1.0):
                GRID.set_node_liquid_water_content(idxNode, theta_r)
                GRID.set_node_ice_fraction(idxNode, 1.0)
            else:
                GRID.set_node_liquid_water_content(idxNode, GRID.get_node_liquid_water_content(idxNode)+dtheta_w)
                GRID.set_node_ice_fraction(idxNode, GRID.get_node_ice_fraction(idxNode)+dtheta_i)

            GRID.set_node_temperature(idxNode, GRID.get_node_temperature(idxNode)+dT)

        else:

            dtheta_i = 0
            dtheta_w = 0

        GRID.set_node_refreeze(idxNode, dtheta_i*GRID.get_node_height(idxNode))
        water_refreezed =  water_refreezed - dtheta_w*GRID.get_node_height(idxNode)

    total_end = np.sum(GRID.get_liquid_water_content())

    #if (total_start-total_end-water_refreezed) > 1e-8:
    #    logger.error('Refreezing module is not mass consistent')
    #    logger.error('Water in the begin/end/refreezed: %2.7f /  %2.7f / %2.7f' % (total_start,total_end,water_refreezed))

    return water_refreezed


