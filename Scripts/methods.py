import arcpy
from arcpy import env, sa

import paths
import cscapeHelper
import distribute

import os
import itertools
import glob

if arcpy.CheckExtension("Spatial") == "Available":
	arcpy.CheckOutExtension("Spatial")
else:
	print "Spatial Analyist license required"
	sys.exit(1)

paths.setEnv(env)
paths.clearTemp()

redoExistingOutput = True

"""
Each distributed function takes in the name of the *output* file it should produce.
(Not the full path, just the filename.)
From this, it determines what input file(s) it needs.

The source and output directories each tool will use, as specified in its docstring,
are given as attribute names of the `paths` module.

If the output file already exists, it will not be overwritten, unless redoExistingOutput is True.
"""

@distribute.remote
def preprocess(layerName):
	"""
	Source dir: resistances
	Output dir: preprocessed
	"""
	paths.setEnv(env)
	env.overwriteOutput = True

	source = paths.join(paths.resistances, layerName)
	output = paths.join(paths.preprocessed, layerName)
	print "Preprocessing {}: {} ==> {}".format(layerName, source, output)

	if arcpy.Exists(output) and not redoExistingOutput:
		print "{} already exists, leaving it as is.".format(output)
		return output

	for tempras in ["projected", "clipped"]:
		try:
			arcpy.Raster(tempras)
			print "Deleting temporary: {}".format(tempras)
			arcpy.Delete_management(tempras)
		except RuntimeError:
			pass  # tempfile doesn't exist, we're good

	print "Projecting and resampling..."
	arcpy.ProjectRaster_management(source, "projected", paths.alaskaAlbers, cell_size= 500)

	source = arcpy.Raster(source)
	print "Initial extent:      {} {} {} {}".format(source.extent.XMin,
											   source.extent.YMin,
											   source.extent.XMax,
											   source.extent.YMax)

	newExt = arcpy.Describe(paths.studyArea).extent
	print "New intended extent: {} {} {} {}".format(newExt.XMin,
										   newExt.YMin,
										   newExt.XMax,
										   newExt.YMax)
	print "Clipping..."
	# TODO: despite specifying an extent, it refuses to clip to exactly that (except by filling in borders with NoData)
	arcpy.Clip_management("projected", "", "clipped", paths.studyArea, "", "ClippingGeometry", "NO_MAINTAIN_EXTENT")
	clipped = arcpy.Raster("clipped")
	
	print "New actual extent:   {} {} {} {}".format(clipped.extent.XMin,
										   clipped.extent.YMin,
										   clipped.extent.XMax,
										   clipped.extent.YMax)

	print "Normalizing..."
	outRas = arcpy.Raster("clipped")
	outRas = (outRas - outRas.minimum) / (outRas.maximum - outRas.minimum)
	# de-null
	outRas = sa.Con(sa.IsNull(outRas), 0, outRas)

	env.overwriteOutput = True

	outRas.save(output)
	arcpy.Delete_management("projected")
	arcpy.Delete_management("clipped")
	return output


@distribute.remote
def weightedCostRaster(outputCodeName, layerOrder= None):
	"""
	Source dir: preprocessed
	Output dir: costRasters

	outputCodeName: 1311011.asc where value of each digit |-->  weight
									  index of each digit |-->  layer index in given list
																(so use the same layer order every time in every function!)
	
	layerOrder: ['agl_resis', 'bcmp_resis', 'bestp_resis', ...] --- layer names in order that corresponds to outputCode
	"""

	if layerOrder is None:
		print "No layer order specified, that's kinda important."
		return

	sources = layerOrder
	weights = map(int, list(outputCodeName.replace(".asc", "")) )

	# outputCode = "".join(map(str, weights))
	print "Making weighted cost raster {}".format(outputCodeName)

	paths.setEnv(env)

	output = paths.join(paths.costRasters, outputCodeName)
	if arcpy.Exists(output) and not redoExistingOutput:
		print "{} already exists, leaving it as is.".format(output)
		return output

	active = [ ( paths.join(paths.preprocessed, source), weight ) for source, weight in zip(sources, weights) if weight > 0 ]
	if len(active) <= 1:
		# TODO: add the straight-line-distance raster, so least cost paths don't freak out?
		pass

	costRas = sa.CreateConstantRaster(0.0001, "FLOAT", env.cellSize, env.extent)
	for source, weight in active:
		costRas += sa.Raster(source) * weight

	arcpy.RasterToASCII_conversion(costRas, output)
	arcpy.CalculateStatistics_management(output,
										 x_skip_factor= 30,
										 y_skip_factor= 30)

	return output

@distribute.remote
def LCP(outputWeightCodedShp):
	"""
	Source dir: costRasters
	Output dir: LCPs
	"""

	weightCode = outputWeightCodedShp.split(".")[0]
	source = paths.join(paths.costRasters, weightCode + ".asc")
	output = paths.join(paths.LCPs, outputWeightCodedShp)
	print "Finding least cost paths for weighting {}".format(weightCode)

	if arcpy.Exists(output) and not redoExistingOutput:
		print "{} already exists, leaving it as is.".format(output)
		return output

	paths.setEnv(env)
	if arcpy.Raster(source).minimum is None:
		print "    Calculating statistics for {}...".format(source)
		arcpy.CalculateStatistics_management(source,
											 x_skip_factor= 30,
											 y_skip_factor= 30)
	print "    Calculating cost distance and backlink..."
	costDist = sa.CostDistance(paths.destination, source, out_backlink_raster= "backlink")
	print "    Finding least-cost path..."
	costPath = sa.CostPath(paths.sources, costDist, "backlink", "EACH_ZONE")

	print "    Vectorizing..."
	arcpy.RasterToPolyline_conversion(costPath, output, simplify= "SIMPLIFY")

	arcpy.Delete_management("backlink")

	return output



with open(paths.cscapeSettings) as f:
	cscapeSettings = f.read()
@distribute.remote
def runCircuitscape(outputCurmap):
	"""
	Source dir: costRasters
	Output dir: circuitscape
	"""
	paths.setEnv(env)

	sourceName = outputCurmap
	source = paths.join(paths.costRasters, sourceName)
	output = paths.join(paths.circuitscape, outputCurmap)
	if arcpy.Exists(output) and not redoExistingOutput:
		print "{} already exists, leaving it as is.".format(output)
		return output

	print "Running Circuitscape on weighting {}".format(source)
	settings = cscapeSettings.format(cscapeGrounds= paths.cscapeGrounds,
									 cscapeSources= paths.cscapeSources,
									 workdir= paths.temp,
									 resistance= source)

	tempSettingsFile = paths.temp + "\\settings.ini"
	with open(tempSettingsFile, "w") as f:
		f.write(settings)

	cs_scratch = os.path.join(paths.temp,'cs_scratch')
	if not os.path.exists(cs_scratch):
		os.mkdir(cs_scratch)

	try:
		cscapeHelper.run(tempSettingsFile)
	except (ImportError, RuntimeError) as e:
		print e
		return

	resultRas = paths.join(cs_scratch, "res_curmap.asc")
	arcpy.Copy_management(resultRas, output)
	arcpy.Delete_management(resultRas)
	return output

@distribute.remote
def render(outputWeightCodePNG, outHeight= 2200, subfolder= None, circuitscape= True):
	"""
	Source dir: LCPs, circuitscape
	Output dir: images
	"""

	weightCode = outputWeightCodePNG.split(".png")[0]
	if subfolder is not None:
		output = paths.join(paths.images, subfolder, outputWeightCodePNG)
	else:
		output = paths.join(paths.images, outputWeightCodePNG)
	if arcpy.Exists(output) and not redoExistingOutput:
		print "{} already exists, leaving it as is.".format(output)
		return output

	print "Rendering PNG of weighting {}".format(weightCode)

	paths.setEnv(env)
	print "    Opening {}".format(paths.mxdTemplate)
	mxd = arcpy.mapping.MapDocument(paths.mxdTemplate)
	print "    Getting data frame"
	df = arcpy.mapping.ListDataFrames(mxd, "")[0]

	print "    Computing extent"
	# df.extent = arcpy.Describe(paths.studyArea).extent
	ext = arcpy.Describe(paths.studyArea).extent

	aspect = ext.width / float(ext.height)
	outWidth = int(outHeight * aspect)
	# print "Aspect ratio: {}, outputting {} x {}".format(aspect, outWidth, outHeight)

	# Copy rasters locally---replaceDataSource is ridiculously slow when the new workspace folder has lots of files in it
	lcpGlob = paths.join(paths.LCPs, weightCode) + ".*"
	print "    Caching {}".format(lcpGlob)
	lcpCache = paths.cache(*glob.glob(lcpGlob), subdir= "lcp")

	print "    Replacing LCP layer"
	lcpLayer = arcpy.mapping.ListLayers(mxd, "LCP", df)[0]
	lcpLayer.replaceDataSource(paths.temp + "\\lcp", "NONE", weightCode)

	if circuitscape:
		# Copy rasters locally
		cscapeGlob = paths.join(paths.circuitscape, weightCode) + ".*"
		print "    Caching {}".format(cscapeGlob)
		cscapeCache = paths.cache(*glob.glob(cscapeGlob), subdir= "cscape")

		cscapeLayer = arcpy.mapping.ListLayers(mxd, "Circuitscape", df)[0]
		cscapeLayer.replaceDataSource(paths.temp + "\\cscape", "NONE", weightCode)

		paths.dropcache(cscapeCache)
	else:
		# TODO: def not final behavior, seperating layers should be done better
		# breaks resolveOutputs abstraction
		# remove this immediately after run...

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

		costLayer.visible = True
		lcpLayer.visible = False
		costOutput = paths.join(paths.images, subfolder, "cost", outputWeightCodePNG)
		print "Writing cost to {}".format(costOutput)
		arcpy.mapping.ExportToPNG(mxd, costOutput, "PAGE_LAYOUT",
								  resolution= 400,
								  background_color= "255, 255, 255")
		
		costLayer.visible = False
		lcpLayer.visible = True
		lcpOutput = paths.join(paths.images, subfolder, "LCP", outputWeightCodePNG)
		print "Writing lcp to {}".format(lcpOutput)
		arcpy.mapping.ExportToPNG(mxd, lcpOutput, "PAGE_LAYOUT",
								  resolution= 400,
								  background_color= "255, 255, 255", transparent_color= "255, 255, 255")
		del mxd

		paths.dropcache(lcpCache)
		paths.dropcache(costCache)
		return
		# TODO: this shouldn't break distribute, but it does (costOutput is not an object)
		# return (costOutput, lcpOutput)

	# Display layer weightings in text box
	# textbox = arcpy.mapping.ListLayoutElements(mxd, "TEXT_ELEMENT")[0]
	# if layerOrder is not None:
	# 	weights = list(weightCode)
	# 	weightsTable = [ "{} : {}" for weight, layer in zip(weights, layerOrder) ]
	# 	textbox.text = "Weighting:\r\n\r\n" + "\r\n".join(weightsTable)
	# else:
	# 	textbox.delete()

	print output
	# arcpy.mapping.ExportToPNG(mxd, output, df,
	# 						  df_export_width= outWidth, df_export_height= outHeight,
	# 						  background_color= "255, 255, 255", transparent_color= "255, 255, 255")
	arcpy.mapping.ExportToPNG(mxd, output, "PAGE_LAYOUT",
							  resolution= 400,
							  background_color= "255, 255, 255")

	del mxd

	paths.dropcache(lcpCache)
	return output


def resolveOutputs(conductor, inputDir, outputDir, getDesiredOutputDir, makeOutputFile, **kwargs):
	"""
	When `getDesiredOutputDir` is called with a set of the filenames in `inputDir`,
	it returns an iterable of the filenames that need to exist in outputDir.

	For every output filename that should exist, but doesn't yet,
	`makeOutputFile` will be called with the name of that file, and any kwargs given to `resolveOutputs`.
	"""
	env.workspace = inputDir
	print "    Checking contents of input {}".format(inputDir)
	inputDirContents = set( arcpy.ListDatasets() + arcpy.ListFeatureClasses() + arcpy.ListRasters() )

	outputDirDesiredContents = getDesiredOutputDir(inputDirContents)

	if not os.path.exists(outputDir):
		os.makedirs(outputDir)
	env.workspace = outputDir
	print "    Checking contents of output {}".format(outputDir)
	outputDirContents = set( arcpy.ListDatasets() + arcpy.ListFeatureClasses() + arcpy.ListRasters() )

	needed = set(outputDirDesiredContents) - outputDirContents if not redoExistingOutput else outputDirDesiredContents
	print "*** {} needs:".format(outputDir)
	if len(needed) == 0:
		print "  * Nothing!"
		return []
	else:
		for outfile in needed:
			print "  * " + outfile
	print

	paths.setEnv(env)
	results = conductor( makeOutputFile(outfile, **kwargs) for outfile in needed )
	return results

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

# useLayers = {
# 	'agl_resis'      : 1,
# 	'bcmp_resis'     : 0,
# 	'bestp_resis'    : 0,
# 	'buffer_resis'   : 0,
# 	'camp_resis'     : 0,
# 	'hiker_resis'    : 0,
# 	'jets_resis'     : 0,
# 	'l50_resis'      : 0,
# 	'nfi_resis'      : 0,
# 	'riv_resis'      : 0,
# 	'roads_resis'    : 0,
# 	'sens_resis'     : 0,
# 	'straight_resis' : 1,
# 	'travel_resis'   : 0
# }

weightsAvailable = [0, 2, 8]
# weightsAvailable = [0, 4]

def weightedCostRasterNames(inNames):
	allWeights = itertools.product(weightsAvailable, repeat= len(layers))
	weightsMask = [ useLayers[lyrname] for lyrname in layers ]
	# TODO: mask layers that aren't in inNames

	maskedCosts = [ [weight*mask for weight, mask in zip(weights, weightsMask)] for weights in allWeights ]

	rasterNames = [ "".join(map(str, costs)) + ".asc" for costs in maskedCosts ]

	# remove duplicates (introduced by masking off layers)
	return list(set(rasterNames))


def filterMasked(getDesiredOutputDir):
	def filterWrapper(inNames):
		# for name in names:
		# 	if name.match("\d+(\..+)?"):
		# 		weights = map(int, list(name))
		# 		weightsMask = [ useLayers[lyrname] for lyrname in layers ]
		# 		keep = [ weight*mask for weight, mask in zip(weight, weightsMask)  ]


		filtered = filter(lambda name: useLayers[ os.path.splitext(name)[0] ] == 1, inNames)
		return getDesiredOutputDir(filtered)
	return filterWrapper

def changeExtTo(newExt):
	def changeExtWrapper(inNames):
		return [ os.path.splitext(name)[0] + newExt for name in inNames]
	return changeExtWrapper

	
if __name__ == '__main__':
	conductor = distribute.Conductor()
	redoExistingOutput = True

	
	#############
	## Preprocess
	resolveOutputs(conductor, paths.resistances, paths.preprocessed,
				   filterMasked(lambda inNames: inNames),
				   preprocess)
	"""
	###############################
	## Make all weight combinations
	resolveOutputs(conductor, paths.preprocessed, paths.costRasters,
				   weightedCostRasterNames,
				   weightedCostRaster,
				   layerOrder= layers)

	###################
	## Least Cost Paths
	resolveOutputs(conductor, paths.costRasters, paths.LCPs,
				   changeExtTo(".shp"),
				   LCP)
	
	###############
	## Circuitscape
	resolveOutputs(conductor, paths.costRasters, paths.circuitscape,
				   lambda inNames: inNames,
				   runCircuitscape)
	
	redoExistingOutput = True
	#########
	## Render
	subfolder = "primary_colors_fixed"
	if not os.path.exists(paths.joinNative(paths.images, subfolder, "cost")):
		os.makedirs(paths.join(paths.images, subfolder, "cost"))

	if not os.path.exists(paths.joinNative(paths.images, subfolder, "LCP")):
		os.makedirs(paths.join(paths.images, subfolder, "LCP"))
	resolveOutputs(conductor, paths.LCPs, paths.join(paths.images, subfolder),
				   changeExtTo(".png"),
				   render,
				   subfolder= subfolder,
				   circuitscape= False)
	"""
