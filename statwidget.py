import sys
from glue.core.data_factories import load_data
from glue.core import DataCollection, Hub, HubListener, Data, coordinates
from glue.core.link_helpers import LinkSame
from glue.viewers.image.qt import ImageViewer
from glue_vispy_viewers.volume.volume_viewer import VispyVolumeViewer
from glue.core.message import DataMessage, DataCollectionMessage, SubsetMessage, LayerArtistUpdatedMessage, NumericalDataChangedMessage
from PyQt5.QtCore import QAbstractItemModel, pyqtSignal, QSize, QFile, QIODevice, QModelIndex, Qt, pyqtSlot, QVariant, QItemSelectionModel
from PyQt5.QtWidgets import QSizePolicy, QTreeView, QMessageBox, QRadioButton, QAbstractScrollArea, QSpinBox, QToolButton, QHeaderView, QAbstractItemView, QApplication, QLabel, QTreeView, QComboBox, QCheckBox, QWidget, QPushButton, QHBoxLayout, QFrame, QTableView, QGroupBox, QDialog, QVBoxLayout, QLabel, QGridLayout
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from decimal import getcontext, Decimal
from IPython.display import display, HTML
from PyQt5.QtGui import *
import sys
from qtpy import compat
from glue.icons.qt import helpers
import pandas as pd
from pandas import DataFrame
import numpy as np
from profilestats import profile


class pandasModel(QtCore.QAbstractTableModel):
    # Set up the data in a form that allows it to be added to qt widget
    def __init__(self, df, dc, parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.dc = dc
        self.data_frame = df
        self.subset_labels = []

        # Should factor out for easier maintenance between pandas model and statsgui? 
        # Dict for full data sets
        # key by tuples
        self.uuid_dict = dict()
        # Dict for subsets
        # self.uuid_dict_subsets = dict()
        self.subset_name_index = dict()

        # fill out the dicts
        for d in range(0, len(self.dc)):
            for c in range(0, len(self.dc[d].components)):
                # key by tuple
                key = tuple([self.dc[d].components[c].uuid, -1])
                # for the non subsets, set subset index to -1
                self.uuid_dict[key] = [d, c, -1]
                # don't populate for subsets- uuid are the same
                for s in range(0, len(self.dc[d].subsets)):
                    # key by tuple
                    key = tuple([self.dc[d].subsets[s].components[c].uuid, s])
                    self.uuid_dict[key] = [d, c, s] 
                    # key subset name to index
                    self.subset_name_index[self.dc[d].subsets[s].label] = s  

        # Create an array of subset labels
        for i in range(0, len(self.dc.subset_groups)):
            self.subset_labels.append(self.dc.subset_groups[i].label)
        
        super(pandasModel, self).__init__(parent)      

    def rowCount(self, parent=None):
        return len(self.data_frame.values)

    def columnCount(self, parent=None):
        return self.data_frame.columns.size

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            if role == Qt.BackgroundRole:
                # get the subset
                subset = self.data_frame.values[index.row()][0]
                # get the uuid
                uuid = self.data_frame.values[index.row()][8]
                # Get the subset index
                if (subset == "--"): 
                    subset_index = -1
                else:
                    subset_index = self.subset_name_index[subset]

                # get the data index from the uuid_dict
                key = tuple([uuid, subset_index])

                data_index = self.uuid_dict[key][0]

                transparency = 60
                
                # If it is a subset find the color and color accordingly
                if subset_index != -1:
                    color = self.dc[data_index].subsets[subset_index].style.color
                    q_color = QColor(color)
                    rgb_color = q_color.getRgb()
                    
                    return QBrush(QColor(rgb_color[0], rgb_color[1], rgb_color[2], transparency))
                
                # If it is a dataset find the color and color accordingly 
                else:
                    color = self.dc[data_index].style.color
                    q_color = QColor(color)
                    rgb_color = q_color.getRgb()

                    return QBrush(QColor(rgb_color[0], rgb_color[1], rgb_color[2], transparency))
                
            elif role == Qt.DisplayRole:
                return QVariant(str(
                    self.data_frame.values[index.row()][index.column()]))
        return QVariant()
    
    def headerData(self, col, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return QVariant(self.data_frame.columns[col])
        if orientation == Qt.Vertical and role == Qt.DisplayRole:
            return QVariant(self.data_frame.index[col])
        return QVariant()  
    
    def sort(self, column, order):
        colname = self.data_frame.columns.tolist()[column]
        self.layoutAboutToBeChanged.emit()
        self.data_frame.sort_values(colname, ascending= order == QtCore.Qt.AscendingOrder, inplace=True)
        self.data_frame.reset_index(inplace=True, drop=True)
        self.layoutChanged.emit()   
        
        
class StatsGui(QWidget, HubListener):
    ''' 
    This class accepts a glue data collection object, and builds an interactive window
    to display basic statistics (e.g. mean, median, mode) about each dataset
    '''
    # @profile(print_stats=20, dump_stats=True)
    def __init__(self, dc):

        # Initialize the object as a QWidget with a HubListener
        QWidget.__init__(self)
        HubListener.__init__(self)  
        
        self.setWindowFlags(Qt.Tool)

        # Set no_update to true
        self.no_update = True
        
        # Save the datacollection object as an attribute of class StatsGui
        self.dc = dc

        # Remove pixel components
        # Is there a less time-costly way to do this? 
        for i in range(0, len(self.dc)):
            # all_components = self.dc[i].components
            if type(self.dc[i].coords) is coordinates.Coordinates:
                keep_components = self.dc[i].main_components + self.dc[i].derived_components
            else:
                keep_components = self.dc[i].main_components + self.dc[i].derived_components + self.dc[i].world_component_ids
            remove = np.setdiff1d(self.dc[i].components, keep_components)
            for j in range(0, len(remove)):
                self.dc[i].remove_component(remove[j])

        # Save the subset names
        self.sub_names = []
        for i in range(len(self.dc.subset_groups)):
            self.sub_names.append(self.dc.subset_groups[i].label)

        # Save the dataset names
        self.data_names = self.dc.labels

        # Save the component names 
        self.all_comp_names = []
        component_names = []
        for i in range(0, len(self.dc)):
            for j in range(0, len(self.dc[i].components)):
                component_names.append(self.dc[i].components[j].label)
            self.all_comp_names.append(component_names)
            component_names = []

        # Keys tuple([uuid, subset index (-1 if full dataset)]) to [data index, component index, subset index]
        self.uuid_dict = dict()

        for d in range(0, len(self.dc)):
            for c in range(0, len(self.dc[d].components)):
                # for the non subsets, set subset index to -1
                # create tuple for key 
                key = tuple([self.dc[d].components[c].uuid, -1])
                self.uuid_dict[key] = [d, c, -1]
                for s in range(0, len(self.dc[d].subsets)):
                    # create tuple for key
                    key = tuple([self.dc[d].subsets[s].components[c].uuid, s])
                    self.uuid_dict[key] = [d, c, s]                   

        # Set the title of the main GUI window
        self.setWindowTitle('Statistics')
        
        # Set up dicts for row indices
        self.subset_dict = dict()
        self.component_dict = dict()
        
        self.selected_dict = dict()
        self.selected_indices = []

        # Initialize model_subsets and model_components to None
        self.model_subsets = None
        self.model_components = None
        
        # Set up the count for number of components/tree rows
        self.num_rows = 0
        
        # Set up the headings
        self.headings = ('Subset', 'Dataset', 'Component', 'Mean', 'Median', 'Minimum', 'Maximum', 'Sum', 'uuid')
        
        # Set up the QTableView Widget
        self.table = QTableView(self)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        
        # Set the table headings   
        self.data_frame = pd.DataFrame(columns=self.headings) 
        # set up data accruate to use the heading list with uuid
        self.data_accurate = pd.DataFrame(columns=self.headings)

        self.model = pandasModel(self.data_frame, self.dc)

        self.table.setModel(self.model) 
        # Hide uuid
        self.table.setColumnHidden(8, True);
        
        # Set up tree view and fix it to the top half of the window
        self.treeview = QTreeView(self)
        self.treeview.setUniformRowHeights(True)

        # Set the default clicking behavior to be row selection
        self.treeview.setSelectionBehavior(QAbstractItemView.SelectRows)
        
        # Layout for collapse/expand and sort tree
        layout_top_left = QHBoxLayout()

        # Layout for select/deselect options
        layout_bottom_left = QHBoxLayout()
        
        self.expand_data = QPushButton(self)
        self.expand_data.setText("Expand all data and subsets")
        self.expand_data.clicked.connect(self.expandClicked)
        layout_top_left.addWidget(self.expand_data)
        
        self.visible = QPushButton(self)
        self.visible.setText("Select all visible")
        self.visible.clicked.connect(self.visibleClicked)
        layout_bottom_left.addWidget(self.visible)
        
        self.all = QPushButton(self)
        self.all.setText('Select all')
        self.all.clicked.connect(self.allClicked)
        layout_bottom_left.addWidget(self.all)
        
        self.none = QPushButton(self)
        self.none.setText('Deselect all')
        self.none.clicked.connect(self.noneClicked)
        layout_bottom_left.addWidget(self.none)
        
        # Set component_mode to false, default is subset mode
        self.component_mode = False

        # These will only be true when the treeview has to switch between views and a
        # Change has been made in the other
        self.updateSubsetSort = False
        self.updateComponentSort = False
        
        # Set up dict for keying treeview labels to items in subset view
        self.subset_label_item = dict()
        # Set up dict for keying treeview labels to items in component view
        self.component_label_item = dict()

        # Sort by subsets as a default
        self.sortBySubsets()
        
        # Add white lines between consecutive selected items
        self.treeview.setStyleSheet(
         "QTreeView::item {border: 0.5px solid #ffffff;}"
        + "QTreeView::item:selected {background: #0269D9;}"
        + "QTreeView::item:selected {color: #ffffff;}"
        + "QTreeView::branch:selected {background: #ffffff;}")
        
        # Set default significant figures to 5
        getcontext().prec = 5
        
        # Set up past selected items
        self.past_selected = []
        self.past_items = []

        # Set up bottom options layout
        layout_bottom_options = QHBoxLayout()
        
        self.siglabel = QLabel(self)
        self.siglabel.setText('Number of decimals:')
        layout_bottom_options.addWidget(self.siglabel)
        
        self.num_sigs = 3
        
        self.sigfig = QSpinBox(self)
        self.sigfig.setRange(1, 10)
        self.sigfig.setValue(self.num_sigs)
        self.sigfig.valueChanged.connect(self.sigchange)
        layout_bottom_options.addWidget(self.sigfig)
        layout_bottom_options.addStretch()
        
        # Allow user to pick scientific notation or nonscientific notation
        self.sci_notation = QRadioButton(self)
        self.sci_notation.setText('Scientific notation')
        self.sci_notation.setChecked(True)
        self.isSci = True
        self.sci_notation.toggled.connect(self.notation)
        
        self.stan_notation = QRadioButton(self)
        self.stan_notation.setText('Decimal notation')
        self.sci_notation.toggled.connect(self.notation)
        
        layout_bottom_options.addWidget(self.sci_notation)
        layout_bottom_options.addWidget(self.stan_notation)
        
        # Export to file button
        self.export = QPushButton(self)
        self.export.setText('Export to file')
        self.export.clicked.connect(self.exportToFile)
        layout_bottom_options.addWidget(self.export)
        
        # Set up the toggle button to switch tree sorting modes
        self.switch_mode = QPushButton(self)
        self.switch_mode.setText('Sort tree by components')
        self.switch_mode.clicked.connect(self.switchMode)
        layout_top_left.addWidget(self.switch_mode)
        
        # Add instructions to sort the table
        self.how = QLabel(self)
        self.how.setText('Click each column name to sort')
        # Make it a slightly lighter color
        self.how.setForegroundRole(QPalette.Mid)
        
        layout_table = QHBoxLayout()
        layout_table.addWidget(self.table)
        layout_table.stretch(10)

        # Set up top options layout
        layout_left = QVBoxLayout()
        layout_left.addLayout(layout_top_left)
        layout_left.addLayout(layout_bottom_left)
        layout_left.addWidget(self.how)

        # Finish nesting all the layouts
        main_layout = QVBoxLayout()
        
        main_layout.addWidget(self.treeview)
        main_layout.addLayout(layout_left)
        main_layout.addLayout(layout_table)
        main_layout.addLayout(layout_bottom_options)
        
        self.setLayout(main_layout)
        
        # Maybe simplify with one dict that keys by tuple[uuid, subset number (-1 if full dataset)]
        # Set up dict for caching full dataset data
        self.cache_stash = dict()

            # Allow the widget to listen for messages
        # dc.hub.subscribe(self, SubsetUpdateMessage, handler=self.receive_message)

        # Change this so that different types of messages are handled differently
        self.dc.hub.subscribe(self, DataMessage, handler=self.dataMessage)
        self.dc.hub.subscribe(self, SubsetMessage, handler=self.subsetMessage)  
        self.dc.hub.subscribe(self, DataCollectionMessage, handler=self.dcMessage)
        self.dc.hub.subscribe(self, LayerArtistUpdatedMessage, handler=self.layerMessage)
        self.dc.hub.subscribe(self, NumericalDataChangedMessage, handler=self.numDataMessage)
    
    def myPressedEvent (self, currentQModelIndex):
        ''' 
        Every time the selection in the treeview changes:
        if it is newly selected, add it to the table
        if it is newly deselected, remove it from the table
        '''

        # Get the indexes of all the selected components
        self.selected_indices = self.treeview.selectionModel().selectedRows()

        # Set up items arrays so that key can be accessed
        self.selected_items = []
        if self.component_mode:
            for index in self.selected_indices:
                self.selected_items.append(self.model_components.itemFromIndex(index))
        else:
            for index in self.selected_indices:
                self.selected_items.append(self.model_subsets.itemFromIndex(index))            

        new_items = np.setdiff1d(self.selected_items, self.past_items)

        for i in range(0, len(new_items)):
            # key by tuple
            key = new_items[i].data()
            self.runStats(key)

        dropped_items = np.setdiff1d(self.past_items, self.selected_items)
            
        for i in range (0, len(dropped_items)):
            key = dropped_items[i].data()

            data_i = self.uuid_dict[key][0]
            comp_i = self.uuid_dict[key][1]
            subset_i = self.uuid_dict[key][2]

            # key[0] is the uuid (key is tuple([uuid, index of subset (-1 if not a subset)]))
            idxu = np.where(self.data_frame['uuid'] == key[0])[0]

            if (subset_i == -1):
                # not a subset
                idxs = np.where(self.data_frame['Subset'] == '--')[0]
            else:
                idxs = np.where(self.data_frame['Subset'] == self.dc.subset_groups[subset_i].label)[0]

            idx = np.intersect1d(idxu, idxs)[0]

            self.data_frame = self.data_frame.drop(idx)
        
        # Update the past selected indices
        self.past_items = self.selected_items
    
        model = pandasModel(self.data_frame, self.dc)
        self.table.setModel(model)
        self.table.setColumnHidden(8, True);
    

    def runStats (self, key):
        '''
        Runs statistics for subsets or full data sets
        '''

        data_i = self.uuid_dict[key][0]
        comp_i = self.uuid_dict[key][1]
        subset_i = self.uuid_dict[key][2]

        data_label = self.dc[data_i].label
        comp_label = self.dc[data_i].components[comp_i].label

        if (subset_i == -1):
            subset_label = "--"
        else:
            subset_label = self.dc[data_i].subsets[subset_i].label

        # See if the values have already been cached
        if self.no_update and key in self.cache_stash:
            column_data = self.cache_stash[key]
        else:
            if (subset_i == -1):
                column_data = self.newDataStats(key)
            else:
                column_data = self.newSubsetStats(key)  
     
        self.buildDataFrame(column_data, data_label, comp_label, subset_label)
    

    # This decorator can be used to profile a function by time
    # @profile(print_stats=20, dump_stats=True)
    def newDataStats(self, key):
        # take in a tuple
        # Generates new data for a dataset that has to be calculated

        subset_label = "--"

        data_i = self.uuid_dict[key][0]
        comp_i = self.uuid_dict[key][1]

        data_label = self.dc[data_i].label
        comp_label = self.dc[data_i].components[comp_i].label

        # Find the stat values
        # Save the data in the cache 
        # use indices extracted earlier from uuid
        mean_val = self.dc[data_i].compute_statistic('mean', self.dc[data_i].components[comp_i])
        median_val = self.dc[data_i].compute_statistic('median', self.dc[data_i].components[comp_i])     
        min_val = self.dc[data_i].compute_statistic('minimum', self.dc[data_i].components[comp_i])     
        max_val = self.dc[data_i].compute_statistic('maximum', self.dc[data_i].components[comp_i])    
        sum_val = self.dc[data_i].compute_statistic('sum', self.dc[data_i].components[comp_i])

        # can this be an array no transpose?
        column_data = np.asarray([[subset_label], [data_label], [comp_label], [mean_val], [median_val], [min_val], [max_val], [sum_val], [key[0]]]).transpose()
            
        self.cache_stash[key] = column_data

        return column_data


    def newSubsetStats(self, key):
        # Generates new data for a subset that needs to be calculated
        # takes in a tuple ([uuid, subset index])

        # # generate the indices from the uuid_val and the uuid_dict
        data_i = self.uuid_dict[key][0]
        comp_i = self.uuid_dict[key][1]
        subset_i = self.uuid_dict[key][2]

        data_label = self.dc[data_i].label
        comp_label = self.dc[data_i].components[comp_i].label
        subset_label = self.dc[data_i].subsets[subset_i].label

        mean_val = self.dc[data_i].compute_statistic('mean', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc[data_i].subsets[subset_i].subset_state)
        median_val = self.dc[data_i].compute_statistic('median', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc.subset_groups[subset_i].subset_state)       
        min_val = self.dc[data_i].compute_statistic('minimum', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc.subset_groups[subset_i].subset_state)       
        max_val = self.dc[data_i].compute_statistic('maximum', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc.subset_groups[subset_i].subset_state)      
        sum_val = self.dc[data_i].compute_statistic('sum', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc.subset_groups[subset_i].subset_state) 

        column_data = np.asarray([[subset_label], [data_label], [comp_label], [mean_val], [median_val], [min_val], [max_val], [sum_val], [key[0]]]).transpose()

        # key by tuple
        self.cache_stash[key] = column_data  

        return column_data


    def buildDataFrame(self, column_data, data_label, comp_label, subset_label):
        # Save the data in self.data_accurate
        column_df = pd.DataFrame(column_data, columns=self.headings)
        self.data_accurate = self.data_accurate.append(column_df, ignore_index=True)        
        
        # Format correctly- factor out? 
        if self.isSci:
            # Format in scientific notation
            string = "%." + str(self.num_sigs) + 'E'
        else:
            # Format in standard notation
            string = "%." + str(self.num_sigs) + 'F'            
            
        mean_val = string % Decimal(column_data[0][3])
        median_val = string % Decimal(column_data[0][4])
        min_val = string % Decimal(column_data[0][5])
        max_val = string % Decimal(column_data[0][6])
        sum_val = string % Decimal(column_data[0][7])
        uuid_val = column_data[0][8]
        
        # Create the column data array and append it to the data frame
        column_data = np.asarray([[subset_label], [data_label], [comp_label], [mean_val], [median_val], [min_val], [max_val], [sum_val], [uuid_val]]).transpose()
        column_df = pd.DataFrame(column_data, columns=self.headings)
        self.data_frame = self.data_frame.append(column_df, ignore_index=True) 
    

    def sigchange(self, i):
        # Set the number of significant figures according to what the user selects
        getcontext().prec = i
        self.num_sigs = i
        
        self.notation()


    def notation(self):
        # Changes the data from scientific to standard notation and vice versa
        
        data_labels = self.data_frame['Dataset']
        comp_labels = self.data_frame['Component']
        subset_labels = self.data_frame['Subset']
        
        mean_vals = []
        median_vals = []
        min_vals = []
        max_vals = []
        sum_vals = []
        uuid_vals = []
        
        if self.stan_notation.isChecked():
            self.isSci = False
            # Build string to format in standard notation
            string = "%." + str(self.num_sigs) + 'F'
        else:
            self.isSci = True
            # Build string to format in scientific notation
            string = "%." + str(self.num_sigs) + 'E'    
            
        for i in range(0, len(self.data_frame)):
            # Traverse through the dataframe and get the names of the component, dataset, and subset

            uuid_val = self.data_frame['uuid'][i]
            subset_val = self.data_frame['Subset'][i]
                
            # find all the indexes where the uuid is that (could be multiple places bc of subsets)
            idxu = np.where(self.data_accurate['uuid'] == uuid_val)[0]
            # find all the indices for that subset
            idxs = np.where(self.data_accurate['Subset'] == subset_val)[0]

            # get the intersect
            idx2 = np.intersect1d(idxu, idxs)[0]
                
            # Format the data in data_accurate
            mean_vals.append(string % Decimal(self.data_accurate['Mean'][idx2]))
            median_vals.append(string % Decimal(self.data_accurate['Median'][idx2]))
            min_vals.append(string % Decimal(self.data_accurate['Minimum'][idx2]))
            max_vals.append(string % Decimal(self.data_accurate['Maximum'][idx2]))
            sum_vals.append(string % Decimal(self.data_accurate['Sum'][idx2])) 
            uuid_vals.append(uuid_val)
           
        # Build the column_data and update the data_frame
        column_data = np.asarray([subset_labels, data_labels, comp_labels, mean_vals, median_vals, min_vals, max_vals, sum_vals, uuid_vals]).transpose()
        self.data_frame = pd.DataFrame(column_data, columns=self.headings)

        model = pandasModel(self.data_frame, self.dc)

        self.table.setModel(model)
        self.table.setColumnHidden(8, True)


    # Either expands or collapses the tree
    def expandClicked(self):
        if self.expand_data.text() == "Expand all data and subsets":
            self.treeview.expandAll()
            self.expand_data.setText("Collapse all data and subsets")
        else:
            self.treeview.collapseAll()
            self.expand_data.setText("Expand all data and subsets")


    def visibleClicked(self):
        # Select all visible components
        
        original_idx = self.treeview.selectionModel().selectedRows()

        self.treeview.selectAll()
        
        # Get all the currently selected rows
        end_idx = self.treeview.selectionModel().selectedRows()
        
        # Check to see if any new rows were selected
        new_rows = np.setdiff1d(end_idx, original_idx)
        
        if len(new_rows) == 0:
            # Tell the user that no new rows were selected
            text = "No new rows are visible."
 
            # Initialize a widget for the message box
            message_widget = QWidget()
 
            # Show a message box with above text, and Close to close the window
            result = QMessageBox.information(message_widget, 'Message', text, QMessageBox.Close, QMessageBox.Close)
        
            # Initialize application
            message_app = QApplication.instance()
            if message_app is None:
                message_app = QApplication(sys.argv)
            else:
                print('QApplication instance already exists: %s' % str(message_app))
 
            # Show window
            message_widget.show() 

        else:
            self.treeview.selectAll()
            

    def allClicked(self):
        # Expand and select all components
        # If more than 20 rows will be added, ask user if they'd like to continue or cancel
        
        # Find what rows are already selected
        original_idx = self.treeview.selectionModel().selectedRows()
        
        # Warn user if they are about to add more than 20 rows to the table
        num_to_add = self.num_rows - len(original_idx)
        
        if num_to_add > 20:
                
            text = "Are you sure you want to add " + str(num_to_add) + " rows to the table?"
 
            # Initialize a widget for the message box
            message_widget = QWidget()
 
            # Show a message box with above text, Yes, and Cancel with Cancel default selected
            result = QMessageBox.warning(message_widget, 'Message', text, QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
 
            if result == QMessageBox.Yes:
                # Go ahead and expand and select all
                self.treeview.expandAll()
                
                # Set expand/collapse button to allow user to collapse rows
                self.expand_data.setText("Collapse all data and subsets")           
                self.treeview.selectAll()
                      
            # Initialize application
            message_app = QApplication.instance()
            if message_app is None:
                message_app = QApplication(sys.argv)
            else:
                print('QApplication instance already exists: %s' % str(message_app))
 
            # Show window
            message_widget.show() 


    def noneClicked(self):
        # Clear the selection from the tree
        self.treeview.clearSelection()
        self.past_items = []
        
        # Clear the table
        self.data_frame = pd.DataFrame(columns=self.headings)
        model = pandasModel(self.data_frame, self.dc)
        self.table.setModel(model)
        self.table.setColumnHidden(8, True)
        

    def exportToFile(self):
        file_name, fltr = compat.getsavefilename(caption="Choose an output filename")
        
        try:
            self.data_frame.to_csv(str(file_name), index=False)
        except:
            pass
        

    def switchMode(self):
        # if the user clicks to sort by components, change the text to "sort by subsets" and sort tree by components
        if self.switch_mode.text() == 'Sort tree by components':
            self.sortByComponents()
            self.switch_mode.setText('Sort tree by subsets')
        # otherwise the user wants to sort by subsets, change text to "sort by components" and sort tree by subsets
        else:
            self.sortBySubsets()
            self.switch_mode.setText('Sort tree by components')
    

    def sortBySubsets(self):
        '''
        Sorts the treeview by subsets- Dataset then subset then component.
        What we originally had as the default
        '''
        # Set to not component mode
        self.component_mode = False
        
        # Clear the num_rows (this keeps track of number of rows to warn the user when they try to add too many)
        self.num_rows = 0
        
        # Save the selected rows from the component view
        if (self.selected_indices != None):
            selected = []

            for i in range(0, len(self.selected_indices)):
                item = self.model_components.itemFromIndex(self.selected_indices[i])
                key = item.data();
                selected.append(key)

        # Clear the selection
        self.noneClicked()

        # Set Expand/collapse button to "expand all"
        self.expand_data.setText("Expand all data and subsets")       
        
        #Allow the user to select multiple rows at a time 
        self.selection_model = QAbstractItemView.MultiSelection
        self.treeview.setSelectionMode(self.selection_model)
        
        # See if the model already exists and doesn't need to be updated
        if self.no_update and not self.updateSubsetSort:
            if self.model_subsets == None:
                self.generateSubsetView()
            else:
                self.treeview.setModel(self.model_subsets)  
        else:
            self.generateSubsetView()
        
        # Make the table update whenever the selection in the tree is changed
        selection_model = QItemSelectionModel(self.model_subsets)
        self.treeview.setSelectionModel(selection_model)
        selection_model.selectionChanged.connect(self.myPressedEvent)

        # Select rows that should be selected
        for i in range(0, len(selected)):
            key = selected[i]
            index = self.subset_dict[key]
            self.treeview.setCurrentIndex(index)
    
        # Update the past_selected and selected_indices
        self.past_selected = self.treeview.selectionModel().selectedRows()
        self.selected_indices = self.treeview.selectionModel().selectedRows()

    def generateSubsetView(self):
        self.component_mode = False
        self.model_subsets = QStandardItemModel()
        self.model_subsets.setHorizontalHeaderLabels([''])

        self.treeview.setModel(self.model_subsets)
        # self.treeview.setUniformRowHeights(True)

        # populate the tree
        # Make all the datasets be parents, and make it so they are not selectable
        parent_data = QStandardItem('{}'.format('Data'))
        parent_data.setEditable(False)
        parent_data.setSelectable(False)

        # Use uuid's to populate the tree?
        # Non-subset data components
        for i in range(0, len(self.dc)):
            parent = QStandardItem('{}'.format(self.dc.labels[i]))
            parent.setData(tuple([self.dc[i].uuid, -1]))
            parent.setIcon(helpers.layer_icon(self.dc[i]))
            parent.setEditable(False)
            parent.setSelectable(False)

            # Make all the data components be children, nested under their parent
            for j in range(0,len(self.dc[i].components)):
                child = QStandardItem('{}'.format(str(self.dc[i].components[j])))
                child.setEditable(False)

                # also save whether its a subset (-1 in this case)
                child.setData(tuple([self.dc[i].components[j].uuid, -1]))

                child.setIcon(helpers.layer_icon(self.dc[i]))
                
                parent.appendRow(child)
                self.num_rows = self.num_rows + 1

            parent_data.appendRow(parent)

        # Add the parents with their children to the QStandardItemModel
        self.model_subsets.appendRow(parent_data)

        parent_subset = QStandardItem('{}'.format('Subsets')) 
        parent_subset.setEditable(False)
        parent_subset.setSelectable(False)

        # Set up the subsets as Subsets > choose subset > choose data set > choose component

        # Subset data components
        for j in range(0, len(self.dc.subset_groups)):
            grandparent = QStandardItem('{}'.format(self.dc.subset_groups[j].label))
            grandparent.setIcon(helpers.layer_icon(self.dc.subset_groups[j]))

            grandparent.setEditable(False)
            grandparent.setSelectable(False)

            for i in range(0, len(self.dc)):
                parent = QStandardItem('{}'.format(self.dc.subset_groups[j].label) + ' (' + '{}'.format(self.dc[i].label) + ')')

                # Set up the circles
                parent.setIcon(helpers.layer_icon(self.dc.subset_groups[j]))
                parent.setEditable(False)
                parent.setSelectable(False)

                try:
                    self.dc[i].compute_statistic('mean', self.dc[i].subsets[j].components[0], subset_state=self.dc[i].subsets[j].subset_state)

                except:
                    parent.setForeground(QtGui.QBrush(Qt.gray))

                for k in range(0, len(self.dc[i].components)):

                    child = QStandardItem('{}'.format(str(self.dc[i].components[k])))
                    # save subset group as well in data
                    child.setData(tuple([self.dc[i].components[k].uuid, j]))
                    child.setEditable(False)
                    child.setIcon(helpers.layer_icon(self.dc.subset_groups[j]))                  
                        
                    parent.appendRow(child)
                    self.num_rows = self.num_rows + 1

                    # Make gray and unselectable components that aren't defined for a subset
                    try:
                        self.dc[i].compute_statistic('mean', self.dc[i].subsets[j].components[k], subset_state=self.dc[i].subsets[j].subset_state)

                    except:
#                             print("Glue has raised an Incompatible Attribute error on this component. Let's do this instead.")
                        child.setEditable(False)
                        child.setSelectable(False)
                        child.setForeground(QtGui.QBrush(Qt.gray))

                grandparent.appendRow(parent) 
            parent_subset.appendRow(grandparent)
        self.model_subsets.appendRow(parent_subset)
        
        # Fill out the dict now that the indices are connected to the QStandardItemModel
        # self.subset_dict keys data of a child (uuid) to the index in the tree

        # Full datasets
        for i in range(0, parent_data.rowCount()):
            # key label to item for message handling
            self.addToLabelItem(parent_data.child(i))

            for j in range(0, parent_data.child(i).rowCount()):
                # key label to item for message handling
                self.addToLabelItem(parent_data.child(i).child(j))

                key = parent_data.child(i).child(j).data()
                self.subset_dict[key] = parent_data.child(i).child(j).index()
            
        # # Subsets
        for i in range(0, parent_subset.rowCount()):
            # key label to item for message handling
            self.addToLabelItem(parent_subset.child(i))

            for j in range(0, parent_subset.child(i).rowCount()):
                # key label to item for message handling
                self.addToLabelItem(parent_subset.child(i).child(j))  

                for k in range(0, parent_subset.child(i).child(j).rowCount()):
                    # key label to item for message handling
                    self.addToLabelItem(parent_subset.child(i).child(j).child(k))

                    key = parent_subset.child(i).child(j).child(k).data()
                    self.subset_dict[key] = parent_subset.child(i).child(j).child(k).index()


    def addToLabelItem(self, item):
        # adds an item to self.subset_label_item or self.component_label_item
        # get the correct dict
        if (self.component_mode):
            mydict = self.component_label_item
        else:
            mydict = self.subset_label_item

        # check if key exists in dict
        if item.text() in mydict:
            # get current array
            arr = mydict[item.text()]
            # add the new item to the array
            arr.append(item)
            # set the array to be the value of the dict
            mydict[item.text()] = arr

        # if not create a new array
        else:
            mydict[item.text()] = [item]

        
    def sortByComponents(self):
        '''
        Sorts the treeview by components- Dataset then component then subsets
        '''  
        # Set component_mode to true
        self.component_mode = True
        
        # Clear the num_rows (this is used to warn the user if they try to select too many things)
        self.num_rows = 0
        
        # Save the selected rows from the subset view if applicable
        if (self.model_subsets != None):
            selected = []

            for i in range(0, len(self.selected_indices)):
                item = self.model_subsets.itemFromIndex(self.selected_indices[i])
                key = item.data()
                selected.append(key)
        
        # Clear the selection
        self.noneClicked()

        # Set Expand/collapse button to "expand all"
        self.expand_data.setText("Expand all data and subsets")
        
        # See if the model already exists and doesn't need to be updated
        if self.no_update and not self.updateComponentSort:
            if self.model_components == None:
                self.generateComponentView()
            else:
                self.treeview.setModel(self.model_components)
        else:
            self.generateComponentView()

        # Make the table update whenever the tree selection is changed
        selection_model = QItemSelectionModel(self.model_components)
        self.treeview.setSelectionModel(selection_model)
        selection_model.selectionChanged.connect(self.myPressedEvent)

        # Goes through previously selected rows
        for i in range(0, len(selected)):
            # Gets the key (the uuid) from the dict
            key = selected[i]
            # Gets the index using the component_dict
            index = self.component_dict[key]
            # select the row
            self.treeview.setCurrentIndex(index)
    
        # Update the past_selected and selected_indices
        self.past_selected = self.treeview.selectionModel().selectedRows() 
        self.selected_indices = self.treeview.selectionModel().selectedRows()

        
    def generateComponentView(self):
        self.component_mode = True
        self.model_components = QStandardItemModel()    
        self.model_components.setHorizontalHeaderLabels([''])

        self.treeview.setModel(self.model_components)
        # self.treeview.setUniformRowHeights(True)

        # Populate the tree
        # Make all the datasets be parents, and make it so they are not selectable
        for i in range(0,len(self.dc)):
            grandparent = QStandardItem('{}'.format(self.dc.labels[i]))
            grandparent.setIcon(helpers.layer_icon(self.dc[i]))
            # grandparent.setData(tuple([self.dc[i].uuid, -1]))
            grandparent.setEditable(False)
            grandparent.setSelectable(False)
            
            # Make all the data components be children, nested under their parent
            for k in range(0,len(self.dc[i].components)):
                parent = QStandardItem('{}'.format(str(self.dc[i].components[k])))
                parent.setEditable(False)
                parent.setSelectable(False)
                
                child = QStandardItem('{}'.format('All data (' + self.dc.labels[i] + ')'))
                # these are not the subset groups so subset gets -1 in data
                child.setData(tuple([self.dc[i].components[k].uuid, -1]))
                child.setIcon(helpers.layer_icon(self.dc[i]))
                child.setEditable(False)
                child.setIcon(helpers.layer_icon(self.dc[i]))

                parent.appendRow(child)
                self.num_rows = self.num_rows + 1
                
                for j in range(0, len(self.dc.subset_groups)):
                    child = QStandardItem('{}'.format(self.dc.subset_groups[j].label))
                    # also set subset index in data
                    child.setData(tuple([self.dc[i].subsets[j].components[k].uuid, j]))
                    child.setEditable(False)
                    child.setIcon(helpers.layer_icon(self.dc.subset_groups[j]))
                        
                    try:
                        self.dc[i].compute_statistic('mean', self.dc[i].subsets[j].components[k], subset_state=self.dc[i].subsets[j].subset_state)

                    except:
#                       print("Glue has raised an Incompatible Attribute error on this component. Let's do this instead.")
                        child.setEditable(False)
                        child.setSelectable(False)
                        child.setForeground(QtGui.QBrush(Qt.gray)) 

                    parent.appendRow(child)
                    self.num_rows = self.num_rows + 1
                
                grandparent.appendRow(parent)
            self.model_components.appendRow(grandparent)
                
            # Fill out the dict now that the indices are connected to the QStandardItemModel
            for i in range(0, grandparent.rowCount()):
                self.addToLabelItem(grandparent.child(i))

                for j in range(0, grandparent.child(i).rowCount()):
                    self.addToLabelItem(grandparent.child(i).child(j))

                    key = grandparent.child(i).child(j).data()
                    self.component_dict[key] = grandparent.child(i).child(j).index()
    
      
    def subsetStateUpdate(self, subset):
        # Find the indices of that subset in the treeview and uncheck/recheck in treeview
        # myPressedEvent and run stats will handle the rest

        # Match the uuids to an array of data/component/subset indices
        # for d in range(0, len(self.dc)):
        #     for s in range(0, len(self.dc[d].subsets)):
        #         for c in range(0, len(self.dc[d].components)):
        #             # will need to change this to key by tuple
        #             self.uuid_dict[self.dc[d].subsets[s].components[c].uuid] = [d, c, s]
        self.no_update = False

        selected_items = []
        indices = []
        no_update_indices = []
        self.selected_indices = self.treeview.selectionModel().selectedRows()
        # print("LENGTH OF SELECTED INDICES subsetStateUpdate: ", len(self.selected_indices))
        # self.past_selected = self.treeview.selectionModel().selectedRows()

        if self.component_mode:
            for i in range(0, len(self.selected_indices)):
                # Get the selected items
                selected_items.append(self.model_components.itemFromIndex(self.selected_indices[i]))
                # If it's the right subset, add it to the indices
                if selected_items[i].text() == subset:
                    # print(selected_items[i].text(), selected_items[i].parent().text())
                    indices.append(self.selected_indices[i])
                else:
                    no_update_indices.append(self.selected_indices[i])

        else:
            for i in range(0, len(self.selected_indices)):
                # Get the selected items
                selected_items.append(self.model_subsets.itemFromIndex(self.selected_indices[i]))
                # Get the names of the selected items
                if selected_items[i].parent().parent().text() == subset:
                    indices.append(self.selected_indices[i])
                else:
                    no_update_indices.append(self.selected_indices[i])

        # Clear the treeview
        self.noneClicked()

        # Reselect the updated subset rows
        for index in indices:
            # Reselect in treeview, triggering stats to recalculate
            self.treeview.setCurrentIndex(index)
        #     # self.myPressedEvent(self.treeview.currentIndex())

        self.no_update = True
        # Reselect the other rows that don't need update
        for index in no_update_indices:
            self.treeview.setCurrentIndex(index)


    def dataMessage(self, message):
        print("dataMessage:")
        print("{0}".format(message))
        # print(message.sender)
        # print(message.sender.uuid)
        # relabel things in the tree and the table

        # this doesn't work to do that
        self.clearAndReselect()


    def clearAndReselect(self):
        # when data name changes, deselect and reselect in table
        self.no_update = False

        if self.component_mode:
            model = self.model_components
            mydict = self.component_dict
        else:
            model = self.model_subsets
            mydict = self.subset_dict

        selected = []

        for i in range(0, len(self.selected_indices)):
            item = model.itemFromIndex(self.selected_indices[i])
            key = item.data()
            selected.append(key)

        # clear selection
        self.noneClicked()

        # Reselect
        for i in range(0, len(selected)):
            # Gets the key (the uuid) from the dict
            key = selected[i]
            # Gets the index using the component_dict
            index = self.mydict[key]
            # select the row
            self.treeview.setCurrentIndex(index)


    def subsetMessage(self, message):
        print("subsetMessage:")
        print("{0}".format(message))

        print("dict: ")
        if self.component_mode:
            print(self.component_label_item)
        else:
            print(self.subset_label_item)

        # Get subset name
        index1 = str(message).index("Sent from: Subset: ") + len("Sent from: Subset: ")
        index2 = str(message).index(" (data: ")
        subset_name = str(message)[index1:index2]

        # Handle an updated subset state
        if "Updated subset_state" in str(message):
            # Redo the stats
            self.subsetStateUpdate(subset_name)  

        # Handle an updated name change
        if "Updated label" in str(message):
            # handle updated name change
            print("subset name has been updated")
            # get new subset names
            new_subs = []
            for i in range(0, len(self.dc.subset_groups)):
                new_subs.append(self.dc.subset_groups[i].label)

                # Compare the new subsets to the old subsets
                # Find what is in old that is no longer in new
                old_label = np.setdiff1d(self.sub_names, new_subs)

                # Save the subset names
                self.sub_names = new_subs
            print("old label: ", old_label)
            print("new label: ", subset_name)
            # iterate through keys in self.component_label_item or self.subset_label_item
            # keys are labels of qtreeview items, values are an array of items with that label

            # if the key contains the old label, change the key to the new label

            # may also need to deselect and reselect indices to update the labels in the table
            # can use self.clearAndReselect()
            # deselect and reselect those indices to update the labels in the table


    def dcMessage(self, message):
        print("dcMessage:")
        print("{0}".format(message))
        # Not sure when this gets triggered


    def layerMessage(self, message):
        # Gets triggered when the color is changed
        # icons need to be updated
        # color in table changes automatically

        # Update the icons in the tree
        print("layerMessage:")

        print("{0}".format(message))
        if (self.component_mode):
            # this technically works but is slow and inefficient
            self.generateComponentView();
        else:
            self.generateSubsetView();
        # To do this more efficiently:
        # get name of dataset or subset

        # iterate through keys in string label to item dict
        # self.component_label_item and self.subset_label_item key treeview labels 
        # to items in the treeview, but they won't catch all the components that have
        # icons 

        # reset icon for any associated with that dataset or subset


    def numDataMessage(self, message):
        # Gets triggered when the numerical data is changed
        # Can solve with similar approach as subsetStateUpdate
        print("numDataMessage:")
        print("{0}".format(message))


    # Note: an additional mess of code was down here that I deleted
    # - had scraps of code that handled various other messaging situations. 
    # Potentially useful as a reference: https://github.com/laurachapman/gluesummer/commit/0f42fca7bca1665c50659fa2a00b62a087ab2bb4

