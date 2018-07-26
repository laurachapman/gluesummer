from glue.config import menubar_plugin
from statswidget import StatsGui

@menubar_plugin("Show stats")
def my_plugin(session, data_collection):
    ex = StatsGui(data_collection)
    ex.show()
