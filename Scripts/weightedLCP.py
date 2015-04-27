import arcpy
from arcpy import sa
from arcpy import env

import os
import sys
import itertools

arcpy.ImportToolbox("Z:\\GJoseph\\Denali\\DenaliJobs.tbx")

def log(msg):
    print msg
    arcpy.AddMessage(msg)

def printEnv(env):
    log( "*** Environment:" )
    for attr in env._environments:
        # log( attr )
        log( "{}: {}".format(attr, getattr(env, attr)) )


def weightedLCP(weightedSumTable, focalNodes, sourceNodesQuery, destNodesQuery, extent, coordSys, cellSize, outputPaths, outputCostRaster= None, prePreProcessed= False):
    printEnv(env)
    log("")
    log("*** Arguments:")

    log( "weightedSumTable: " + str(weightedSumTable) )
    log( "focalNodes: " + str(focalNodes) )
    log( "sourceNodesQuery: " + str(sourceNodesQuery) )
    log( "destNodesQuery: " + str(destNodesQuery) )
    log( "extent: " + str(extent) )
    log( "coordSys: " + str(coordSys) )
    log( "cellSize: " + str(cellSize) )
    log( "outputPaths: " + str(outputPaths) )
    log( "outputCostRaster: " + str(outputCostRaster) )
    log( "prePreProcessed: " + str(prePreProcessed) )

    log("***")

    # Preprocess
    table = [ row.split(' ') for row in weightedSumTable.split(';') ]
    rasters, fields, weights = zip(*table)
    if not prePreProcessed:


        log("Preprocessing {}...".format(' '.join(rasters)))
        preprocessed = [ arcpy.DenaliJobs.Preprocess(arcpy.Raster(raster),
                                                     extent,
                                                     coordSys,
                                                     cellSize) for raster in rasters ]
    
        table = sa.WSTable( zip(preprocessed, fields, weights) )
    else:
        log("Skipping preprocessing")
        rasters = map(arcpy.Raster, rasters)
        table = sa.WSTable( zip(rasters, fields, weights) )

    # Weighted sum
    log("Computing weighted sum...")
    costRaster = sa.WeightedSum(table)
    if outputCostRaster is not None:
        costRaster.save(outputCostRaster)

    # LCP
    log("Computing least cost paths...")
    paths = arcpy.DenaliJobs.LCP(costRaster, focalNodes, sourceNodesQuery, destNodesQuery, outputPaths)

    return paths

if __name__ == '__main__':
    argv = tuple(arcpy.GetParameterAsText(i) for i in range(arcpy.GetArgumentCount()))
    weightedLCP(*argv)
