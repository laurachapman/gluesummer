import sys
from glue.core.data_factories import load_data
from glue.core import DataCollection
from glue.core.link_helpers import LinkSame
from glue.app.qt.application import GlueApplication
from glue.viewers.image.qt import ImageViewer
from glue_vispy_viewers.volume.volume_viewer import VispyVolumeViewer

image_filename='w5.fits'
catalog_filename='w5_psc.vot'

#load 2 datasets from files
catalog = load_data(catalog_filename)
image = load_data(image_filename)

dc = DataCollection([catalog,image])

# link positional information
dc.add_link(LinkSame(catalog.id['RAJ2000'], image.id['Right Ascension']))
dc.add_link(LinkSame(catalog.id['DEJ2000'], image.id['Declination']))

#Create subset based on filament mask
ra_state=(image.id['Right Ascension'] > 44) & (image.id['Right Ascension'] < 46)
subset_group=dc.new_subset_group('RA_Selection',ra_state)
subset_group.style.color = '#0000FF'

#start Glue
app = GlueApplication(dc)

imageviewer = app.new_data_viewer(ImageViewer)
imageviewer.add_data(image)

app.start()

