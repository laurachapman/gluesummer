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


class pandasModel(QtCore.QAbstractTableModel):
    # Set up the data in a form that allows it to be added to qt widget
    def __init__(self, df, dc, parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.dc = dc
        self.data_frame = df
        self.subset_labels = []
        
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
                # Get the data index and set the tranparency
                data = str(self.data_frame.values[index.row()][1])
                data_index = np.where(data == np.asarray(self.dc.labels))[0][0]  
                transparency = 60
                
                # If it is a subset find the color and color accordingly
                if self.data_frame.values[index.row()][0] != '--':
                    subset = str(self.data_frame.values[index.row()][0])
                    subset_index = np.where(subset == np.asarray(self.subset_labels))[0][0]
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
        for i in range(0, len(self.dc)):
            all_components = self.dc[i].components
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

        # Match the uuids to an array of data/component/subset indices
        self.uuid_dict = dict()
        for d in range(0, len(self.dc)):
            for c in range(0, len(self.dc[d].components)):
                self.uuid_dict[self.dc[d].components[c].uuid] = [d, c, -1]
                for s in range(0, len(self.dc[d].subsets)):
                    self.uuid_dict[self.dc[d].subsets[s].components[c].uuid] = [d, c, s]                   

        # Set the title of the main GUI window
        self.setWindowTitle('Statistics')
        
        # Set up dicts for row indices
        self.subset_dict = dict()
        self.component_dict = dict()
        
        self.selected_dict = dict()
        self.selected_indices = []
        
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
        
        # Set the table headings   
        self.data_frame = pd.DataFrame(columns=self.headings) 
        self.data_accurate = pd.DataFrame(columns=self.headings)
        self.model = pandasModel(self.data_frame, self.dc)

        self.table.setModel(self.model) 
        
        # Set up tree view and fix it to the top half of the window
        self.treeview = QTreeView(self)
        
        # Set the default clicking behavior to be row selection
        self.treeview.setSelectionBehavior(QAbstractItemView.SelectRows)
        
        # Set up expand all, collapse all, select all and deselect all buttons
        
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
        # # Right align by adding stretch
        # layout_bottom_left.addStretch()
        # layout_bottom_left.addWidget(self.how)
        
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
        
        # Set up dict for caching
        self.cache_stash = dict()
        # Set up dict for matching uuids to items in the treeview
        # self.subset_uuid_to_item = dict()
        self.component_uuid_to_item = dict()
    
            # Allow the widget to listen for messages
#         dc.hub.subscribe(self, SubsetUpdateMessage, handler=self.receive_message)
        self.dc.hub.subscribe(self, DataMessage, handler=self.messageReceived)
        self.dc.hub.subscribe(self, SubsetMessage, handler=self.messageReceived)  
        self.dc.hub.subscribe(self, DataCollectionMessage, handler=self.messageReceived)
        self.dc.hub.subscribe(self, LayerArtistUpdatedMessage, handler=self.messageReceived)
        self.dc.hub.subscribe(self, NumericalDataChangedMessage, handler=self.messageReceived)
    
    def myPressedEvent (self, currentQModelIndex):
        ''' 
        Every time the selection in the treeview changes:
        if it is newly selected, add it to the table
        if it is newly deselected, remove it from the table
        '''

        # Get the indexes of all the selected components
        self.selected_indices = self.treeview.selectionModel().selectedRows()

        # Set up items arrays so that uuid can be accessed
        self.selected_items = []
        if self.component_mode:
            for index in self.selected_indices:
                self.selected_items.append(self.model_components.itemFromIndex(index))
        else:
            for index in self.selected_indices:
                self.selected_items.append(self.model_subsets.itemFromIndex(index))            

        new_items = np.setdiff1d(self.selected_items, self.past_items)

        for i in range(0, len(new_items)):
            uuid_val = new_items[i].data()

            data_i = self.uuid_dict[uuid_val][0]
            comp_i = self.uuid_dict[uuid_val][1]
            subset_i = self.uuid_dict[uuid_val][2]

            print("d,c,s indices in added: ", data_i, comp_i, subset_i)
            is_subset = (subset_i != -1)

            # Check if its a subset and if so run subset stats
            if is_subset: 
                self.runSubsetStats(subset_i, data_i, comp_i, uuid_val)
            else:
                # Run standard data stats
                self.runDataStats(data_i, comp_i, uuid_val) 

        dropped_items = np.setdiff1d(self.past_items, self.selected_items)
            
        for i in range (0, len(dropped_items)):
            uuid_val = dropped_items[i].data()

            data_i = self.uuid_dict[uuid_val][0]
            comp_i = self.uuid_dict[uuid_val][1]
            subset_i = self.uuid_dict[uuid_val][2]

            print("d,c,s indices in dropped: ", data_i, comp_i, subset_i)
            is_subset = (subset_i != -1)

            try:
                idx2 = np.where(self.data_frame['uuid'] == uuid_val)[0][0]
                print(idx2)

                self.data_frame = self.data_frame.drop(idx2)
            except:
                pass
        
        # Update the past selected indices
        self.past_items = self.selected_items
        
        model = pandasModel(self.data_frame, self.dc)
        
        self.table.setModel(model)
       
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)  
    
    def runDataStats (self, data_i, comp_i, uuid_val):
        '''
        Runs statistics for the component comp_i of data set data_i
        '''
        subset_label = "--"
        data_label = self.dc[data_i].label   
        comp_label = self.dc[data_i].components[comp_i].label # add to the name array to build the table
        uuid_val = self.dc[data_i].components[comp_i].uuid
        
        # Build the cache key
        # cache_key = subset_label + data_label + comp_label
        cache_key = uuid_val
        
        # See if the values have already been cached
        if self.no_update:
            try:
                column_data = self.cache_stash[cache_key]
            except:
                column_data = self.newDataStats(data_i, comp_i, uuid_val)
        else:
            column_data = self.newDataStats(data_i, comp_i, uuid_val)    
     
        # Save the accurate data in self.data_accurate
        column_df = pd.DataFrame(column_data, columns=self.headings)
        self.data_accurate = self.data_accurate.append(column_df, ignore_index=True)        

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

        # Create the column data array and append it to the data frame
        column_data = np.asarray([[subset_label], [data_label], [comp_label], [mean_val], [median_val], [min_val], [max_val], [sum_val], [uuid_val]]).transpose()
        column_df = pd.DataFrame(column_data, columns=self.headings)
        self.data_frame = self.data_frame.append(column_df, ignore_index=True)
    
    def newDataStats(self, data_i, comp_i, uuid_val):
        # Generates new data for a dataset that has to be calculated

        subset_label = "--"
        data_label = self.dc[data_i].label   
        comp_label = self.dc[data_i].components[comp_i].label # add to the name array to build the table
        # uuid_val = self.dc[data_i].components[comp_i].uuid
        
        # Build the cache key
        # cache_key = subset_label + data_label + comp_label
        cache_key = uuid_val

        # Find the stat values
        # Save the data in the cache 
        mean_val = self.dc[data_i].compute_statistic('mean', self.dc[data_i].components[comp_i])
        median_val = self.dc[data_i].compute_statistic('median', self.dc[data_i].components[comp_i])     
        min_val = self.dc[data_i].compute_statistic('minimum', self.dc[data_i].components[comp_i])     
        max_val = self.dc[data_i].compute_statistic('maximum', self.dc[data_i].components[comp_i])    
        sum_val = self.dc[data_i].compute_statistic('sum', self.dc[data_i].components[comp_i])
        uuid_val = self.dc[data_i].components[comp_i].uuid

        column_data = np.asarray([[subset_label], [data_label], [comp_label], [mean_val], [median_val], [min_val], [max_val], [sum_val], [uuid_val]]).transpose()
            
        self.cache_stash[cache_key] = column_data

        return column_data

    def runSubsetStats (self, subset_i, data_i, comp_i, uuid_val):
        '''
        Runs statistics for the subset subset_i with respect to the component comp_i of data set data_i
        '''

        subset_label = self.dc[data_i].subsets[subset_i].label
        data_label = self.dc[data_i].label   
        comp_label = self.dc[data_i].components[comp_i].label # add to the name array to build the table
        
        # Build the cache key
        # cache_key = subset_label + data_label + comp_label
        cache_key = uuid_val

        # See if the statistics are already in the cache if nothing needs to be updated
        
        if self.no_update:
            try:
                column_data = self.cache_stash[cache_key]
            except:
                column_data = self.newSubsetStats(subset_i, data_i, comp_i)
        else:
            column_data = self.newSubsetStats(subset_i, data_i, comp_i)
        
        # Save the data in self.data_accurate
        column_df = pd.DataFrame(column_data, columns=self.headings)
        self.data_accurate = self.data_accurate.append(column_df, ignore_index=True)        
        
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
        
        # Create the column data array and append it to the data frame
        column_data = np.asarray([[subset_label], [data_label], [comp_label], [mean_val], [median_val], [min_val], [max_val], [sum_val], [uuid_val]]).transpose()
        column_df = pd.DataFrame(column_data, columns=self.headings)
        self.data_frame = self.data_frame.append(column_df, ignore_index=True)  

    def newSubsetStats(self, subset_i, data_i, comp_i, uuid_val):
        # Generates new data for a subset that needs to be calculated
        subset_label = self.dc[data_i].subsets[subset_i].label
        data_label = self.dc[data_i].label   
        comp_label = self.dc[data_i].components[comp_i].label # add to the name array to build the table

        # Build the cache key
        # cache_key = subset_label + data_label + comp_label
        cache_key = uuid_val

        mean_val = self.dc[data_i].compute_statistic('mean', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc[data_i].subsets[subset_i].subset_state)
        median_val = self.dc[data_i].compute_statistic('median', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc.subset_groups[subset_i].subset_state)       
        min_val = self.dc[data_i].compute_statistic('minimum', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc.subset_groups[subset_i].subset_state)       
        max_val = self.dc[data_i].compute_statistic('maximum', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc.subset_groups[subset_i].subset_state)      
        sum_val = self.dc[data_i].compute_statistic('sum', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc.subset_groups[subset_i].subset_state) 
        uuid_val = self.dc[data_i].subsets[subset_i].components[comp_i].uuid

        column_data = np.asarray([[subset_label], [data_label], [comp_label], [mean_val], [median_val], [min_val], [max_val], [sum_val], [uuid_val]]).transpose()

        self.cache_stash[cache_key] = column_data  

        return column_data
    
    def sigchange(self, i):
        # Set the number of significant figures according to what the user selects
        getcontext().prec = i
        self.num_sigs = i
        
        # Retrospectively change the number of significant figures in the table
        
        data_labels = self.data_frame['Dataset']
        comp_labels = self.data_frame['Component']
        subset_labels = self.data_frame['Subset']
        
        mean_vals = []
        median_vals = []
        min_vals = []
        max_vals = []
        sum_vals = []
        
        if self.isSci:
            # Build a string that will format numbers in scientific notation
            string = "%." + str(self.num_sigs) + 'E'
        else:
            # Build a string that will format numbers in standard notation
            string = "%." + str(self.num_sigs) + 'F'    
    
        # Get the values from the self.data_accurate array and append them
        for i in range (0, len(self.data_frame)):
            uuid_val = self.data_frame['uuid'][i]
               
            idx2 = self.data_accurate['uuid'].index(uuid_val)
                
            # Append the values to the stat arrays, formatted with the string built above
            mean_vals.append(string % Decimal(self.data_accurate['Mean'][idx2]))
            median_vals.append(string % Decimal(self.data_accurate['Median'][idx2]))
            min_vals.append(string % Decimal(self.data_accurate['Minimum'][idx2]))
            max_vals.append(string % Decimal(self.data_accurate['Maximum'][idx2]))
            sum_vals.append(string % Decimal(self.data_accurate['Sum'][idx2]))               
           
        # Build the column_data
        column_data = np.asarray([subset_labels, data_labels, comp_labels, mean_vals, median_vals, min_vals, max_vals, sum_vals]).transpose()
        
        # Update the self.data_frame
        self.data_frame = pd.DataFrame(column_data, columns=self.headings)
        model = pandasModel(self.data_frame, self.dc)
        self.table.setModel(model)
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)        
        
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
        
        # Clear the table
        self.data_frame = pd.DataFrame(columns=self.headings)
        model = pandasModel(self.data_frame, self.dc)
        self.table.setModel(model)
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)
        
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
        
        # Clear the num_rows
        self.num_rows = 0
        
        # Clear the data_accurate
        self.data_accurate = pd.DataFrame(columns=self.headings)      
        
        # Save the selected rows from the component view
        try:
            selected = dict()
            for i in range(0, len(self.selected_indices)):
                item = self.model_components.itemFromIndex(self.selected_indices[i])
                if item.row() != 0:
                    # key = item.text() + " (" + item.parent().parent().text() + ")"+ item.parent().text()
                    key = item.parent.data()
                    selected[key] = item.index()
                else:
                    # key = item.text() + item.parent().text()
                    key = item.parent().data()
                    selected[key] = item.index() 
        except:
            pass
        
        # Clear the selection
        self.treeview.clearSelection()
        
        # Set Expand/collapse button to "expand all"
        self.expand_data.setText("Expand all data and subsets")       
        
        #Allow the user to select multiple rows at a time 
        self.selection_model = QAbstractItemView.MultiSelection
        self.treeview.setSelectionMode(self.selection_model)
        
        # See if the model already exists and doesn't need to be updated
        
        if self.no_update and not self.updateSubsetSort:
            try:
                self.treeview.setModel(self.model_subsets)
            except:
                self.generateSubsetView()
        else:
            self.generateSubsetView()
        
        self.treeview.setUniformRowHeights(True)
        
        # Make the table update whenever the selection in the tree is changed
        selection_model = QItemSelectionModel(self.model_subsets)
        self.treeview.setSelectionModel(selection_model)
        selection_model.selectionChanged.connect(self.myPressedEvent)

        # Clear the table 
        self.data_frame = pd.DataFrame(columns=self.headings)
        model = pandasModel(self.data_frame, self.dc)
        self.table.setModel(model)
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)
        
        # Select rows that should be selected
        
        sel_mod = self.treeview.selectionModel()
        
        for i in range(0, len(selected)):
            key = list(selected.keys())[i]
            index = self.subset_dict[key]
            self.treeview.setCurrentIndex(index)
    
        self.treeview.setSelectionModel(sel_mod)
        
        # Update the past_selected and selected_indices
        self.past_selected = self.treeview.selectionModel().selectedRows()
        self.selected_indices = self.treeview.selectionModel().selectedRows()
        # print("LENGTH OF SELECTED INDICES sortBySubsets: ", len(self.selected_indices))

    def generateSubsetView(self):
        self.component_mode = False
        self.model_subsets = QStandardItemModel()
        self.model_subsets.setHorizontalHeaderLabels([''])

        self.treeview.setModel(self.model_subsets)
        self.treeview.setUniformRowHeights(True)

        # Match the uuids to an array of data/component/subset indices
        self.uuid_dict = dict()
        for d in range(0, len(self.dc)):
            for c in range(0, len(self.dc[d].components)):
                self.uuid_dict[self.dc[d].components[c].uuid] = [d, c, -1]
                for s in range(0, len(self.dc[d].subsets)):
                    self.uuid_dict[self.dc[d].subsets[s].components[c].uuid] = [d, c, s]   

        print(self.uuid_dict)

        # populate the tree
        # Make all the datasets be parents, and make it so they are not selectable
        parent_data = QStandardItem('{}'.format('Data'))
        parent_data.setEditable(False)
        parent_data.setSelectable(False)

        for i in range(0, len(self.dc)):
            parent = QStandardItem('{}'.format(self.dc.labels[i]))
            parent.setData(self.dc[i].uuid)
            parent.setIcon(helpers.layer_icon(self.dc[i]))
            parent.setEditable(False)
            parent.setSelectable(False)

            # Make all the data components be children, nested under their parent
            for j in range(0,len(self.dc[i].components)):
                child = QStandardItem('{}'.format(str(self.dc[i].components[j])))
                child.setEditable(False)
                child.setData(self.dc[i].components[j].uuid)

                print(child.data(), child.text())

                child.setIcon(helpers.layer_icon(self.dc[i]))
                    
                # Add to the subset_dict
                # key = self.dc[i].label + self.dc[i].components[j].label + "All data-" + self.dc[i].label
                key = child.data()
                self.subset_dict[key] = child.index()

                # # Add to the uuid to item dict
                # self.subset_uuid_to_item[self.dc[i].components[j].uuid] = child
                
                parent.appendRow(child)
                self.num_rows = self.num_rows + 1

            parent_data.appendRow(parent)

        # Add the parents with their children to the QStandardItemModel
        self.model_subsets.appendRow(parent_data)

        parent_subset = QStandardItem('{}'.format('Subsets')) 
        parent_subset.setEditable(False)
        parent_subset.setSelectable(False)

        # Set up the subsets as Subsets > choose subset > choose data set > choose component

        for j in range(0, len(self.dc.subset_groups)):
            grandparent = QStandardItem('{}'.format(self.dc.subset_groups[j].label))
            grandparent.setIcon(helpers.layer_icon(self.dc.subset_groups[j]))
            grandparent.setData(self.dc.subset_groups[j].uuid)

            grandparent.setEditable(False)
            grandparent.setSelectable(False)

            for i in range(0, len(self.dc)):
                parent = QStandardItem('{}'.format(self.dc.subset_groups[j].label) + ' (' + '{}'.format(self.dc[i].label) + ')')

                # Set up the circles
                parent.setIcon(helpers.layer_icon(self.dc.subset_groups[j]))
                parent.setData(self.dc.subset_groups[j].uuid)
                parent.setEditable(False)
                parent.setSelectable(False)

                try:
                    self.dc[i].compute_statistic('mean', self.dc[i].subsets[j].components[0], subset_state=self.dc[i].subsets[j].subset_state)

                except:
                    parent.setForeground(QtGui.QBrush(Qt.gray))

                for k in range(0, len(self.dc[i].components)):

                    child = QStandardItem('{}'.format(str(self.dc[i].components[k])))
                    child.setData(self.dc[i].components[k].uuid)
                    child.setEditable(False)
                    child.setIcon(helpers.layer_icon(self.dc.subset_groups[j]))
                        
                    # Update the dict to keep track of row indices
                    # key = self.dc[i].label + self.dc[i].components[k].label + self.dc[i].subsets[j].label
                    key = child.data()
                    self.subset_dict[key] = child.index()

                    # Add to the uuid to item dict
                    # self.subset_uuid_to_item[self.dc[i].subset_groups[j].components[k].uuid] = child                    
                        
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
            
        # Full datasets
        for i in range(0, parent_data.rowCount()):
            for j in range(0, parent_data.child(i).rowCount()):
                # key = "All data (" + parent_data.child(i).text() + ")"+ parent_data.child(i).child(j).text()
                key = parent_data.child(i).child(j).data()
                self.subset_dict[key] = parent_data.child(i).child(j).index()
            
        # Subsets
        for i in range(0, parent_subset.rowCount()):
            for j in range(0, parent_subset.child(i).rowCount()):
                for k in range(0, parent_subset.child(i).child(j).rowCount()):
                    # key = parent_subset.child(i).child(j).text() + parent_subset.child(i).child(j).child(k).text()
                    key = parent_subset.child(i).child(j).child(k).data()
                    self.subset_dict[key] = parent_subset.child(i).child(j).child(k).index()

        
    def sortByComponents(self):
        '''
        Sorts the treeview by components- Dataset then component then subsets
        '''  
        # Set component_mode to true
        self.component_mode = True
        
        # Clear the num_rows
        self.num_rows = 0
        
        # Clear the data_accurate
        self.data_accurate = pd.DataFrame(columns=self.headings)
        
        # Save the selected rows from the subset view if applicable
        try:
            selected = dict()

            for i in range(0, len(self.selected_indices)):
                item = self.model_subsets.itemFromIndex(self.selected_indices[i])
                if item.parent().parent().text() == "Data":
                    # key =  "All data (" + item.parent().text() + ")" + item.text()
                    key = item.data()
                    selected[key] = item.index()
                else:
                    # key = item.parent().text() + item.text()
                    key = item.data()
                    selected[key] = item.index()
        except:
            pass
        
        # Clear the selection
        self.treeview.clearSelection()
        
        # Set Expand/collapse button to "expand all"
        self.expand_data.setText("Expand all data and subsets")
        
        self.selection_model = QAbstractItemView.MultiSelection
        self.treeview.setSelectionMode(self.selection_model)
        
        # See if the model already exists and doesn't need to be updated
        
        if self.no_update and not self.updateComponentSort:
            try:
                self.treeview.setModel(self.model_components)
            except:
                self.generateComponentView()
        else:
            self.generateComponentView()

        self.treeview.setUniformRowHeights(True)
        
        # Make the table update whenever the tree selection is changed
        selection_model = QItemSelectionModel(self.model_components)
        self.treeview.setSelectionModel(selection_model)
        selection_model.selectionChanged.connect(self.myPressedEvent)
 
        # Clear the table 
        self.data_frame = pd.DataFrame(columns=self.headings)
        model = pandasModel(self.data_frame, self.dc)
        self.table.setModel(model)
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)

        # Select the rows that should be selected

        sel_mod = self.treeview.selectionModel()
    
        for i in range(0, len(selected)):
            key = list(selected.keys())[i]
            index = self.component_dict[key]
            self.treeview.setCurrentIndex(index)
    
        self.treeview.setSelectionModel(sel_mod)
        
        # Update the past_selected and selected_indices
        self.past_selected = self.treeview.selectionModel().selectedRows() 
        self.selected_indices = self.treeview.selectionModel().selectedRows()
        # print("LENGTH OF SELECTED INDICES sortByComponents: ", len(self.selected_indices))
        
    def generateComponentView(self):
        self.component_mode = True
        self.model_components = QStandardItemModel()    
        self.model_components.setHorizontalHeaderLabels([''])

        self.treeview.setModel(self.model_components)
        self.treeview.setUniformRowHeights(True)
    
        # Match the uuids to an array of data/component/subset indices
        self.uuid_dict = dict()
        for d in range(0, len(self.dc)):
            for c in range(0, len(self.dc[d].components)):
                self.uuid_dict[self.dc[d].components[c].uuid] = [d, c, -1]
                for s in range(0, len(self.dc[d].subsets)):
                    self.uuid_dict[self.dc[d].subsets[s].components[c].uuid] = [d, c, s]   
        print(self.uuid_dict)

        # Populate the tree
        # Make all the datasets be parents, and make it so they are not selectable
        
        for i in range(0,len(self.dc)):
            grandparent = QStandardItem('{}'.format(self.dc.labels[i]))
            grandparent.setIcon(helpers.layer_icon(self.dc[i]))
            grandparent.setData(self.dc[i].uuid)
            grandparent.setEditable(False)
            grandparent.setSelectable(False)
            
            # Make all the data components be children, nested under their parent
            for k in range(0,len(self.dc[i].components)):
                parent = QStandardItem('{}'.format(str(self.dc[i].components[k])))
                parent.setData(self.dc[i].components[k].uuid)
                parent.setEditable(False)
                parent.setSelectable(False)
                
                child = QStandardItem('{}'.format('All data (' + self.dc.labels[i] + ')'))
                child.setData(self.dc[i].components[k].uuid)
                child.setIcon(helpers.layer_icon(self.dc[i]))
                child.setEditable(False)
                child.setIcon(helpers.layer_icon(self.dc[i]))

                # Add to the uuid to item dict
                # self.component_uuid_to_item[self.dc[i].components[k].uuid] = child  
                    
                parent.appendRow(child)
                self.num_rows = self.num_rows + 1
                
                for j in range(0, len(self.dc.subset_groups)):
                    child = QStandardItem('{}'.format(self.dc.subset_groups[j].label))
                    child.setData(self.dc[i].subsets[j].components[k].uuid)
                    child.setEditable(False)
                    child.setIcon(helpers.layer_icon(self.dc.subset_groups[j]))
                        
                    try:
                        self.dc[i].compute_statistic('mean', self.dc[i].subsets[j].components[k], subset_state=self.dc[i].subsets[j].subset_state)

                    except:
#                       print("Glue has raised an Incompatible Attribute error on this component. Let's do this instead.")
                        child.setEditable(False)
                        child.setSelectable(False)
                        child.setForeground(QtGui.QBrush(Qt.gray)) 

                    # Add to the uuid to item dict
                    # self.component_uuid_to_item[self.dc[i].subsets[j].components[k].uuid] = child  

                    parent.appendRow(child)
                    self.num_rows = self.num_rows + 1
                
                grandparent.appendRow(parent)
            self.model_components.appendRow(grandparent)
                
            # Fill out the dict now that the indices are connected to the QStandardItemModel
            for i in range(0, grandparent.rowCount()):
                for j in range(0, grandparent.child(i).rowCount()):
                    if grandparent.child(i).child(j).row() == 0:
                        # key = grandparent.child(i).child(j).text() + grandparent.child(i).text()
                        key = grandparent.child(i).data()
                        self.component_dict[key] = grandparent.child(i).child(j).index()
                    else:
                        # key = grandparent.child(i).child(j).text() + " (" + grandparent.text() + ")" + grandparent.child(i).text()
                        key = grandparent.child(i).data()
                        self.component_dict[key] = grandparent.child(i).child(j).index()
            
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
                
            idx2 = self.data_accurate['uuid'].index(uuid_val)
                
            # Format the data in data_accurate
            mean_vals.append(string % Decimal(self.data_accurate['Mean'][idx2]))
            median_vals.append(string % Decimal(self.data_accurate['Median'][idx2]))
            min_vals.append(string % Decimal(self.data_accurate['Minimum'][idx2]))
            max_vals.append(string % Decimal(self.data_accurate['Maximum'][idx2]))
            sum_vals.append(string % Decimal(self.data_accurate['Sum'][idx2])) 
           
        # Build the column_data and update the data_frame
        column_data = np.asarray([subset_labels, data_labels, comp_labels, mean_vals, median_vals, min_vals, max_vals, sum_vals]).transpose()
        self.data_frame = pd.DataFrame(column_data, columns=self.headings)
        model = pandasModel(self.data_frame, self.dc)
        self.table.setModel(model)
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)
      
    def subsetStateUpdate(self, subset):
        # Find the indices of that subset in the treeview and uncheck/recheck in treeview
        # myPressedEvent and run stats will handle the rest

        # Match the uuids to an array of data/component/subset indices
        for d in range(0, len(self.dc)):
            for s in range(0, len(self.dc[d].subsets)):
                for c in range(0, len(self.dc[d].components)):
                    self.uuid_dict[self.dc[d].subsets[s].components[c].uuid] = [d, c, s]

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


    def messageReceived(self, message):
        self.no_update = False
        print("Message received:")
        print("{0}".format(message))

        # Handle an updated subset state
        if "Updated subset_state" in str(message):
            # Redo the stats
            # Get the subset that was updated
            # index1 = str(message).index("Sent from: Subset: ") + len("Sent from: Subset: ")
            # index2 = str(message).index(" (data: ")
            # subset_name = str(message)[index1:index2]
            uuid = message.sender.uuid
            for i in range(0, len(self.dc.subset_groups)):
                if self.dc.subset_groups[i].uuid == uuid:
                    subset_name = self.dc.subset_groups[i].label
            self.subsetStateUpdate(subset_name)  

        # Handle the rest of the cases by refreshing the treeview without changing values
        else:
            # Refresh the table and the treeview but don't change stat values
            # selected_indices = self.treeview.selectionModel().selectedRows()
            # TEST to see when selected indices is changing
            selected_indices = self.selected_indices
            # print("LENGTH OF SELECTED INDICES: ", len(selected_indices))

            if self.component_mode:

                if "Updated label" in str(message):
                    # Figure out what in the treeview is no longer in the dataset
                    # For these items, key according to the new label
                    # Subsets only

                    # index1 = str(message).index("Sent from: Subset: ") + len("Sent from: Subset: ")
                    # index2 = str(message).index(" (data: ")
                    # # New name of subset

                    uuid = message.sender.uuid
                    for i in range(0, len(self.dc.subset_groups)):
                        if self.dc.subset_groups[i].uuid == uuid:
                            subset_name = self.dc.subset_groups[i].label
                    subset_name = str(message)[index1:index2]

                    # All new subsets
                    new_subs = []
                    for i in range(0, len(self.dc.subset_groups)):
                        new_subs.append(self.dc.subset_groups[i].label)

                    # Compare the new subsets to the old subsets
                    # Find what is in old that is no longer in new
                    old_label = np.setdiff1d(self.sub_names, new_subs)

                    # Save the subset names
                    self.sub_names = new_subs

                    # Save the selected rows from the component view
                    try:
                        selected = dict()
                        for i in range(0, len(selected_indices)):
                            item = self.model_components.itemFromIndex(selected_indices[i])
                            if item.row() != 0:
                                if item.text() == old_label:
                                # Use updated subset name
                                    # key = subset_name + " (" + item.parent().parent().text() + ")"+ item.parent().text()
                                    key = item.parent().data()
                                else: 
                                    # key = item.text() + " (" + item.parent().parent().text() + ")"+ item.parent().text()
                                    item.parent().data()
                                selected[key] = item.index()
                            else:
                                # key = item.text() + item.parent().text()
                                key = item.parent().data()
                                selected[key] = item.index() 
                    except:
                        pass

                elif "DataUpdateMessage" in str(message):
                    # print("RUNNING DATAUPDATEMESSAGE")
                    # Update for an updated data label
                    index1 = str(message).index("Data Set: ") + len("Data Set: ")
                    index2 = str(message).index("Number of dimensions: ") - 1
                    new_name = str(message)[index1:index2]

                    new_names = self.dc.labels
                    old_name = np.setdiff1d(self.data_names, new_names)[0]

                    # Save the selected rows from the component view
                    try:
                        selected = dict()
                        for i in range(0, len(selected_indices)):

                            item = self.model_components.itemFromIndex(selected_indices[i])

                            # if item.row() != 0:
                            #     if item.parent().parent().text() == old_name:
                            #         key = item.text() + " (" + new_name + ")"+ item.parent().text()
                            #     else:
                            #         key = item.text() + " (" + item.parent().parent().text() + ")"+ item.parent().text()
                            #     selected[key] = item.index()
                            # else:
                            #     if old_name in item.text():
                            #         key = "All data (" + new_name + ")" + item.parent().text()
                            #     else:
                            #         key = item.text() + item.parent().text()
                            #     selected[key] = item.index() 
                            key = item.parent().data()
                            selected[key] = item.index()
                    except:
                        pass

                    # Update the labels
                    self.data_names = self.dc.labels

                elif "DataRenameComponentMessage" in str(message):
                    # Update for an updated component name

                    # Get the name of the dataset where the component was changed
                    index1 = str(message).index("Data Set: ") + len("Data Set: ")
                    index2 = str(message).index("Number of dimensions: ") - 1
                    data_name = str(message)[index1:index2]

                    # Get the index of that dataset
                    # This will create problems if there is more than one dataset with the same name
                    dataset = self.dc.labels.index(data_name)

                    new_names = []
                    # Get the new names of components
                    for i in range(0, len(self.dc[dataset].components)):
                        new_names.append(self.dc[dataset].components[i].label)

                    # Use setdiff1d to get the old name
                    old_name = np.setdiff1d(self.all_comp_names[dataset], new_names)[0]  
                    # Use setdiff1d to get the new name
                    new_name = np.setdiff1d(new_names, self.all_comp_names[dataset])[0]               

                    # Go through key process to assign new keys to the rows that have the old name
                    try:
                        selected = dict()
                        for i in range(0, len(selected_indices)):

                            item = self.model_components.itemFromIndex(selected_indices[i])

                            key = item.parent().data()
                            selected[key] = item.index()
                            # if item.row() != 0:
                            #     if item.parent().text() == old_name:
                            #         key = item.text() + " (" + item.parent().parent().text() + ")"+ new_name
                            #     else:
                            #         key = item.text() + " (" + item.parent().parent().text() + ")"+ item.parent().text()
                            #     selected[key] = item.index()
                            # else:
                            #     if item.parent().text() == old_name:
                            #         key = item.text() + new_name
                            #     else:
                            #         key = item.text() + item.parent().text()
                            #     selected[key] = item.index() 
                    except:
                        pass

                    # Update the component labels 
                    self.all_comp_names = []
                    component_names = []
                    for i in range(0, len(self.dc)):
                        for j in range(0, len(self.dc[i].components)):
                            component_names.append(self.dc[i].components[j].label)
                        self.all_comp_names.append(component_names)
                        component_names = []


                else:
                    # print("RUNNING LAST ELSE")
                    # Save the selected rows from the component view
                    try:
                        selected = dict()
                        for i in range(0, len(selected_indices)):
                            item = self.model_components.itemFromIndex(selected_indices[i])
                            # if item.row() != 0:
                            #     key = item.text() + " (" + item.parent().parent().text() + ")"+ item.parent().text()
                            #     selected[key] = item.index()
                            # else:
                            #     key = item.text() + item.parent().text()
                            #     selected[key] = item.index() 
                            key = item.parent().data()
                            selected[key] = item.index()
                    except:
                        pass


                self.sortByComponents()
                # Program will need to update the sort by subset tree next time it switches
                self.updateSubsetSort = True
                # Sort by components tree is up to date
                self.updateComponentSort = False

                # Select the correct rows 
                for i in range(0, len(selected)):
                    key = list(selected.keys())[i]
                    index = self.component_dict[key]
                    # print("selecting at line 1420")
                    self.treeview.setCurrentIndex(index)               

            # Sort by subsets cases
            else:

                if "Updated label" in str(message):
                # Figure out what in the treeview is no longer in the dataset
                # For these items, key according to the new label
                # Subsets only

                    index1 = str(message).index("Sent from: Subset: ") + len("Sent from: Subset: ")
                    index2 = str(message).index(" (data: ")
                    # New name of subset
                    subset_name = str(message)[index1:index2]

                    # All new subsets
                    new_subs = []
                    for i in range(0, len(self.dc.subset_groups)):
                        new_subs.append(self.dc.subset_groups[i].label)

                    # Compare the new subsets to the old subsets
                    # Find what is in old that is no longer in new
                    old_label = np.setdiff1d(self.sub_names, new_subs)

                    # Save the subset names
                    self.sub_names = new_subs

                    # Save the selected rows from the component view
                    try:
                        selected = dict()
                        for i in range(0, len(selected_indices)):
                            item = self.model_subsets.itemFromIndex(selected_indices[i])
                            key = item.data()
                            selected[key] = item.index()
                            # if item.parent().parent().text() == "Data":
                            #     key =  "All data (" + item.parent().text() + ")" + item.text()
                            #     selected[key] = item.index()
                            # else:
                            #     if item.parent().parent().text() == old_label:
                            #         # Build the correct new key
                            #         index1 = item.parent().text().index("(") - 1
                            #         index2 = item.parent().text().index(")") + 1
                            #         key = subset_name + item.parent().text()[index1:index2] + item.text()
                            #     else:
                            #         key = item.parent().text() + item.text()
                            #     selected[key] = item.index()
                    except:
                        pass

                elif "DataUpdateMessage" in str(message):
                    # Update for an updated data label
                    index1 = str(message).index("Data Set: ") + len("Data Set: ")
                    index2 = str(message).index("Number of dimensions: ") - 1
                    new_name = str(message)[index1:index2]

                    new_names = self.dc.labels
                    old_name = np.setdiff1d(self.data_names, new_names)[0]

                    # Save the selected rows, use updated keys for updated data
                    try:
                        selected = dict()

                        for i in range(0, len(selected_indices)):
                            item = self.model_subsets.itemFromIndex(selected_indices[i])
                            key = item.data()
                            selected[key] = item.index()
                            # if item.parent().parent().text() == "Data":
                            #     if item.parent().text() == old_name:
                            #         key = "All data (" + new_name + ")" + item.text()
                            #     else: 
                            #         key =  "All data (" + item.parent().text() + ")" + item.text()
                            #     selected[key] = item.index()
                            # else:
                            #     if old_name in item.parent().text():
                            #         key = item.parent().parent().text() + " (" + new_name + ")" + item.text()
                            #     else:
                            #         key = item.parent().text() + item.text()
                            #     selected[key] = item.index()
                    except:
                        pass

                    # Update the labels
                    self.data_names = self.dc.labels

                elif "DataRenameComponentMessage" in str(message):
                    # Update for an updated component name

                    # Get the name of the dataset where the component was changed
                    index1 = str(message).index("Data Set: ") + len("Data Set: ")
                    index2 = str(message).index("Number of dimensions: ") - 1
                    data_name = str(message)[index1:index2]

                    # Get the index of that dataset
                    dataset = self.dc.labels.index(data_name)
                    print(dataset, type(dataset))

                    new_names = []
                    # Get the new names of components
                    for i in range(0, len(self.dc[dataset].components)):
                        new_names.append(self.dc[dataset].components[i].label)

                    print("new_names: ", new_names)

                    # Use setdiff1d to get the old name
                    old_name = np.setdiff1d(self.all_comp_names[dataset], new_names)[0]  
                    print("old_name: ", old_name)
                    # Use setdiff1d to get the new name
                    new_name = np.setdiff1d(new_names, self.all_comp_names[dataset])[0]  
                    print("new_name: ", new_name)                  

                    # Go through key process to assign new keys to the rows that have the old name
                    try:
                        selected = dict()

                        for i in range(0, len(selected_indices)):
                            item = self.model_subsets.itemFromIndex(selected_indices[i])
                            key = item.data()
                            selected[key] = item.index()

                            # if item.parent().parent().text() == "Data":
                            #     if item.text() == old_name and item.parent().text() == self.dc[dataset].label:
                            #         key = "All data (" + item.parent().text() + ")" + new_name
                            #         # print("line 1395")
                            #         # print(key)
                            #     else:
                            #         key = "All data (" + item.parent().text() + ")" + item.text()
                            #     selected[key] = item.index()
                            # else:
                            #     if item.text() == old_name and item.parent().text() == self.dc[dataset].label:
                            #         key = item.parent().text() + new_name
                            #         # print("line 1403")
                            #         # print(key)
                            #     else:
                            #         key = item.parent().text() + item.text()
                            #     selected[key] = item.index()

                    except:
                        pass

                    # Update the component labels 
                    self.all_comp_names = []
                    component_names = []
                    for i in range(0, len(self.dc)):
                        for j in range(0, len(self.dc[i].components)):
                            component_names.append(self.dc[i].components[j].label)
                        self.all_comp_names.append(component_names)
                        component_names = []

                else: 
                # Save the selected rows from the subset view if applicable
                    try:
                        selected = dict()

                        for i in range(0, len(selected_indices)):
                            item = self.model_subsets.itemFromIndex(selected_indices[i])
                            key = item.data()
                            selected[key] = item.index()
                            # if item.parent().parent().text() == "Data":
                            #     key =  "All data (" + item.parent().text() + ")" + item.text()
                            #     selected[key] = item.index()
                            # else:
                            #     key = item.parent().text() + item.text()
                            #     selected[key] = item.index()
                    except:
                        pass

                self.sortBySubsets()
                # Program will need to update the sort by component tree next time it switches
                self.updateComponentSort = True
                # Sort by subsets tree is up to date
                self.updateSubsetSort = False

                # Select the correct rows 
                for i in range(0, len(selected)):
                    key = list(selected.keys())[i]
                    index = self.subset_dict[key]
                    # print("selecting at line 1584")
                    self.treeview.setCurrentIndex(index)

        self.no_update = True

