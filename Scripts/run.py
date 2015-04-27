import arcpy
from arcpy import env, sa
import sys
import os

import paths
import distribute

paths.setEnv(env)
tbx = arcpy.ImportToolbox(paths.toolboxPath)
if arcpy.CheckExtension("Spatial") == "Available":
	arcpy.CheckOutExtension("Spatial")
else:
	print "Spatial Analyist license required"
	sys.exit(1)

def log(msg):
    print msg
    arcpy.AddMessage(msg)

# @distribute.remote
def test():
	import time
	print "tested"
	time.sleep(3)
	print "done"
	return 5

# @distribute.remote
def preprocess(raster, output):
	log("Starting preprocess for {} --> {}".format(raster, output))
	prevWorkspace = env.workspace
	env.workspace = paths.preprocessedPath
	preprocessed = tbx.Preprocess(arcpy.Raster(raster),
								  paths.studyAreaPath,
								  env.outputCoordinateSystem,
								  env.cellSize,
								  output)
	log("Complete")
	# preprocessed.save(output)
	log("Saved to %s" % output)
	env.workspace = prevWorkspace
	return preprocessed.catalogPath

# @distribute.remote
def weightedSum(weightedSumTable, output):
	table = sa.WSTable(weightedSumTable)
	costRaster = sa.WeightedSum(table)
	costRaster.save(output)
	return costRaster.catalogPath

# @distribute.remote
def LCP(costRaster, focalNodes, sourceNodesQuery, destNodesQuery, output):
	paths = tbx.LCP(costRaster, focalNodes, sourceNodesQuery, destNodesQuery, output)
	return paths

if __name__ == '__main__':
	# conductor = distribute.Conductor()
	def conductor(x): return list(x)

	weights = {
		'bcmp_resis': '1',
		# 'l50_resis': 1,
		'hiker_resis': '1'
	}

	# # conductor( test() )
	# conductor( conductor.makeTask('test') )

	weightedSumTable = [ [os.path.join(paths.preprocessedPath, raster), "VALUE", weight] for raster, weight in weights.iteritems() ]
	for row in weightedSumTable:
		print row
	# rasters = [ row[0] for row in weightedSumTable ]
	
	# preprocessedOuts = [ os.path.join(paths.preprocessedPath, raster) for raster in weights.iterkeys() ]
	# preprocessedOuts = [ raster for raster in weights.iterkeys() ]

	# preprocessed = conductor( preprocess(raster, out) for raster, out in zip(rasters, preprocessedOuts) )

	costRaster = conductor( weightedSum(weightedSumTable, os.path.join(paths.workspacePath, "cost_raster")) )
