import arcpy
from arcpy import env

import paths
import sys
import glob

paths.clearTemp()

def makePDF(weightCode, mxdPath, outputDir, outHeight= 2200):
	outName = weightCode + ".pdf"
	output = paths.joinNative(outputDir, outName)

	print "Rendering PDF for weight {}".format(weightCode)

	paths.setEnv(env)
	mxd = arcpy.mapping.MapDocument(mxdPath)
	df = arcpy.mapping.ListDataFrames(mxd, "")[0]

	costAsc = paths.join(paths.costRasters, weightCode + ".asc")
	if arcpy.Raster(costAsc).minimum is None:
		print "Calculating statistics for {}".format(costAsc)
		arcpy.CalculateStatistics_management(costAsc,
											 x_skip_factor= 30,
											 y_skip_factor= 30)

	# Copy rasters locally
	costGlob = paths.join(paths.costRasters, weightCode) + ".*"
	print "    Caching {}".format(costGlob)
	costCache = paths.cache(*glob.glob(costGlob), subdir= "cost")

	print "    Replacing cost layer"
	costLayer = arcpy.mapping.ListLayers(mxd, "Cost", df)[0]
	costLayer.replaceDataSource(paths.temp + "\\cost", "NONE", weightCode)

	print "Writing cost to {}".format(output)
	arcpy.mapping.ExportToPDF(mxd, output, "PAGE_LAYOUT", resolution= 400)

	del mxd

	paths.dropcache(costCache)

if __name__ == '__main__':
	layers = [
		'agl_resis',
		'bcmp_resis',
		'bestp_resis',
		'buffer_resis',
		'camp_resis',
		'hiker_resis',
		'jets_resis',
		'l50_resis',
		'nfi_resis',
		'riv_resis',
		'roads_resis',
		'sens_resis',
		'straight_resis',
		'travel_resis'
	]

	# only primary layers on:
	useLayers = {
		'agl_resis'      : 1,
		'bcmp_resis'     : 1,
		'bestp_resis'    : 1,
		'buffer_resis'   : 0,
		'camp_resis'     : 0,
		'hiker_resis'    : 1,
		'jets_resis'     : 0,
		'l50_resis'      : 1,
		'nfi_resis'      : 0,
		'riv_resis'      : 0,
		'roads_resis'    : 0,
		'sens_resis'     : 0,
		'straight_resis' : 1,
		'travel_resis'   : 1
	}

	mxdPath = paths.joinNative(paths.poster, "costmap.mxd")
	outputDir = paths.joinNative(paths.poster, "Graphics", "Costs")

	for i, layer in enumerate(layers):
		if useLayers[layer] == 1:
			weightCode = ['0'] * len(layers)
			weightCode[i] = '2'
			weightCode = ''.join(weightCode)

			makePDF(weightCode, mxdPath, outputDir)
