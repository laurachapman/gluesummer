import sys
from glue.core.data_factories import load_data
from glue.core import DataCollection, Hub, HubListener, Data
from glue.core.link_helpers import LinkSame
from glue.viewers.image.qt import ImageViewer
from glue_vispy_viewers.volume.volume_viewer import VispyVolumeViewer
from glue.core.message import DataMessage, DataCollectionMessage, SubsetMessage
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
        print("Hello")

        # Initialize the object as a QWidget with a HubListener
        QWidget.__init__(self)
        HubListener.__init__(self)  
        
        self.setWindowFlags(Qt.Sheet)

        # Set no_update to true
        self.no_update = True
        
        # Save the datacollection object as an attribute of class StatsGui
        self.dc = dc
        
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
        self.headings = ('Subset', 'Dataset', 'Component', 'Mean', 'Median', 'Minimum', 'Maximum', 'Sum')
        
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
        
        # Allow user to pick scientific notation or nonscientific notation
        self.sci_notation = QRadioButton(self)
        self.sci_notation.setText('Scientific notation')
        self.sci_notation.setChecked(True)
        self.isSci = True
        self.sci_notation.toggled.connect(self.notation)
        
        self.stan_notation = QRadioButton(self)
        self.stan_notation.setText('Standard notation')
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
    
            # Allow the widget to listen for messages
#         dc.hub.subscribe(self, SubsetUpdateMessage, handler=self.receive_message)
        self.dc.hub.subscribe(self, DataMessage, handler=self.messageReceived)
        self.dc.hub.subscribe(self, SubsetMessage, handler=self.messageReceived)  
        self.dc.hub.subscribe(self, DataCollectionMessage, handler=self.messageReceived)
    
    
    def myPressedEvent (self, currentQModelIndex):
        ''' 
        Every time the selection in the treeview changes:
        if it is newly selected, add it to the table
        if it is newly deselected, remove it from the table
        '''
            
        # Get the indexes of all the selected components
        self.selected_indices = self.treeview.selectionModel().selectedRows()

        newly_selected = np.setdiff1d(self.selected_indices, self.past_selected)
            
        for index in range (0, len(newly_selected)):
                
            # Check which view mode the tree is in to get the correct indices
            if not self.component_mode:
                if newly_selected[index].parent().parent().parent().row() == -1:
                    # Whole data sets
                    data_i = newly_selected[index].parent().row()
                    comp_i = newly_selected[index].row()
                    subset_i = -1
                else:
                    # Subsets
                    data_i = newly_selected[index].parent().row()
                    comp_i = newly_selected[index].row()
                    subset_i = newly_selected[index].parent().parent().row()
            
            else:
                data_i = newly_selected[index].parent().parent().row()
                comp_i = newly_selected[index].parent().row()
                subset_i = newly_selected[index].row() - 1

            is_subset = (subset_i != -1)

            # Check if its a subset and if so run subset stats
            if is_subset: 
                self.runSubsetStats(subset_i, data_i, comp_i)

            else:
                # Run standard data stats
                self.runDataStats(data_i, comp_i)   
            
        newly_dropped = np.setdiff1d(self.past_selected, self.selected_indices)
            
        for index in range (0, len(newly_dropped)):
                
            # Check which view mode the tree is in to get the correct indices
            if not self.component_mode:
                data_i = newly_dropped[index].parent().row()
                comp_i = newly_dropped[index].row()
                subset_i = newly_dropped[index].parent().parent().row()
            
            else:
                data_i = newly_dropped[index].parent().parent().row()
                comp_i = newly_dropped[index].parent().row()
                subset_i = newly_dropped[index].row() - 1
            
            is_subset = newly_dropped[index].parent().parent().parent().row() == 1 or (self.switch_mode.text() == 'Sort tree by subsets' and subset_i != -1)

            if is_subset:
                try:
                    # Get the indices that match the component, dataset, and subset requirements
                    idx_c = np.where(self.data_frame['Component'] == self.dc[data_i].components[comp_i].label)
                    idx_d = np.where(self.data_frame['Dataset'] == self.dc[data_i].label)
                    idx_s = np.where(self.data_frame['Subset'] == self.dc[data_i].subsets[subset_i].label)
                    idx1 = np.intersect1d(idx_c, idx_d)
                    idx2 = np.intersect1d(idx1, idx_s)

                    self.data_frame = self.data_frame.drop(idx2)
                except:
                    pass

            else:
                try:
                # Find the index in the table of the unchecked element, if it's in the table

                    # Find the matching component and dataset indices and intersect them to get the unique index
                    idx_c = np.where(self.data_frame['Component'] == self.dc[data_i].components[comp_i].label)
                    idx_d = np.where(self.data_frame['Dataset'] == self.dc[data_i].label)
                    idx_s = np.where(self.data_frame['Subset'] == '--')
                    idx1 = np.intersect1d(idx_c, idx_d)
                    idx2 = np.intersect1d(idx1, idx_s)

                    self.data_frame = self.data_frame.drop(idx2)
                except:
                    pass
        
        # Update the past selected indices
        self.past_selected = self.selected_indices
        
        model = pandasModel(self.data_frame, self.dc)
        
        self.table.setModel(model)
       
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)  
    
    def runDataStats (self, data_i, comp_i):
        '''
        Runs statistics for the component comp_i of data set data_i
        '''

        subset_label = "--"
        data_label = self.dc[data_i].label   
        comp_label = self.dc[data_i].components[comp_i].label # add to the name array to build the table
        
        # Build the cache key
        cache_key = subset_label + data_label + comp_label
        
        # See if the values have already been cached
        try:
            if self.no_update:
                column_data = self.cache_stash[cache_key]
        
        except:         
        # Find the stat values
        # Save the data in the cache 
            mean_val = self.dc[data_i].compute_statistic('mean', self.dc[data_i].components[comp_i])
            median_val = self.dc[data_i].compute_statistic('median', self.dc[data_i].components[comp_i])     
            min_val = self.dc[data_i].compute_statistic('minimum', self.dc[data_i].components[comp_i])     
            max_val = self.dc[data_i].compute_statistic('maximum', self.dc[data_i].components[comp_i])    
            sum_val = self.dc[data_i].compute_statistic('sum', self.dc[data_i].components[comp_i])

            column_data = np.asarray([[subset_label], [data_label], [comp_label], [mean_val], [median_val], [min_val], [max_val], [sum_val]]).transpose()
            
            self.cache_stash[cache_key] = column_data
        
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
        column_data = np.asarray([[subset_label], [data_label], [comp_label], [mean_val], [median_val], [min_val], [max_val], [sum_val]]).transpose()
        column_df = pd.DataFrame(column_data, columns=self.headings)
        self.data_frame = self.data_frame.append(column_df, ignore_index=True)
    
    def runSubsetStats (self, subset_i, data_i, comp_i):
        '''
        Runs statistics for the subset subset_i with respect to the component comp_i of data set data_i
        '''

        subset_label = self.dc[data_i].subsets[subset_i].label
        data_label = self.dc[data_i].label   
        comp_label = self.dc[data_i].components[comp_i].label # add to the name array to build the table
        
        # Build the cache key
        cache_key = subset_label + data_label + comp_label
        
        # See if the statistics are already in the cache
        try:
            if self.no_update:
                column_data = self.cache_stash[cache_key]
        
        # Find the stats if not in the cache
        # Save in the cache
        
        except:
            mean_val = self.dc[data_i].compute_statistic('mean', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc[data_i].subsets[subset_i].subset_state)
            median_val = self.dc[data_i].compute_statistic('median', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc.subset_groups[subset_i].subset_state)       
            min_val = self.dc[data_i].compute_statistic('minimum', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc.subset_groups[subset_i].subset_state)       
            max_val = self.dc[data_i].compute_statistic('maximum', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc.subset_groups[subset_i].subset_state)      
            sum_val = self.dc[data_i].compute_statistic('sum', self.dc[data_i].subsets[subset_i].components[comp_i], subset_state=self.dc.subset_groups[subset_i].subset_state) 

            column_data = np.asarray([[subset_label], [data_label], [comp_label], [mean_val], [median_val], [min_val], [max_val], [sum_val]]).transpose()

            self.cache_stash[cache_key] = column_data
        
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
        column_data = np.asarray([[subset_label], [data_label], [comp_label], [mean_val], [median_val], [min_val], [max_val], [sum_val]]).transpose()
        column_df = pd.DataFrame(column_data, columns=self.headings)
        self.data_frame = self.data_frame.append(column_df, ignore_index=True)    
    
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
            # Traverse through the data_frame, which represents the data in the table
            # Get the name of the component, dataset, and subset of each row  
            component = self.data_frame['Component'][i]
            dataset = self.data_frame['Dataset'][i]
            subset = self.data_frame['Subset'][i]
               
            # Find the index of data_accurate that corresponds to the data
            idx_c = np.where(component == self.data_accurate['Component'])
            idx_d = np.where(dataset == self.data_accurate['Dataset'])
            idx_s = np.where(subset == self.data_accurate['Subset'])
            idx1 = np.intersect1d(idx_c, idx_d)
            idx2 = np.intersect1d(idx1, idx_s)[0] 
                
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
                    key = item.text() + " (" + item.parent().parent().text() + ")"+ item.parent().text()
                    selected[key] = item.index()
                else:
                    key = item.text() + item.parent().text()
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
        
        if self.no_update:
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

    def generateSubsetView(self):
        self.model_subsets = QStandardItemModel()
        self.model_subsets.setHorizontalHeaderLabels([''])

        self.treeview.setModel(self.model_subsets)
        self.treeview.setUniformRowHeights(True)

        # populate the tree
        # Make all the datasets be parents, and make it so they are not selectable
        parent_data = QStandardItem('{}'.format('Data'))
        parent_data.setEditable(False)
        parent_data.setSelectable(False)

        for i in range(0, len(self.dc)):
            parent = QStandardItem('{}'.format(self.dc.labels[i]))
            parent.setIcon(helpers.layer_icon(self.dc[i]))
            parent.setEditable(False)
            parent.setSelectable(False)

            # Make all the data components be children, nested under their parent
            for j in range(0,len(self.dc[i].components)):
                child = QStandardItem('{}'.format(str(self.dc[i].components[j])))
                child.setEditable(False)
                child.setIcon(helpers.layer_icon(self.dc[i]))
                    
                # Add to the subset_dict
                key = self.dc[i].label + self.dc[i].components[j].label + "All data-" + self.dc[i].label
                self.subset_dict[key] = child.index()
                
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
                    child.setEditable(False)
                    child.setIcon(helpers.layer_icon(self.dc.subset_groups[j]))
                        
                    # Update the dict to keep track of row indices
                    key = self.dc[i].label + self.dc[i].components[k].label + self.dc[i].subsets[j].label
                    self.subset_dict[key] = child.index()
                        
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
                key = "All data (" + parent_data.child(i).text() + ")"+ parent_data.child(i).child(j).text()
                self.subset_dict[key] = parent_data.child(i).child(j).index()
            
        # Subsets
        for i in range(0, parent_subset.rowCount()):
            for j in range(0, parent_subset.child(i).rowCount()):
                for k in range(0, parent_subset.child(i).child(j).rowCount()):
                    key = parent_subset.child(i).child(j).text() + parent_subset.child(i).child(j).child(k).text()
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
                    key =  "All data (" + item.parent().text() + ")" + item.text()
                    selected[key] = item.index()
                else:
                    key = item.parent().text() + item.text()
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
        
        if self.no_update:
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
        
    def generateComponentView(self):
        self.model_components = QStandardItemModel()    
        self.model_components.setHorizontalHeaderLabels([''])

        self.treeview.setModel(self.model_components)
        self.treeview.setUniformRowHeights(True)
    
        # Populate the tree
        # Make all the datasets be parents, and make it so they are not selectable
        
        for i in range(0,len(self.dc)):
            grandparent = QStandardItem('{}'.format(self.dc.labels[i]))
            grandparent.setIcon(helpers.layer_icon(self.dc[i]))
            grandparent.setEditable(False)
            grandparent.setSelectable(False)
            
            # Make all the data components be children, nested under their parent
            for k in range(0,len(self.dc[i].components)):
                parent=QStandardItem('{}'.format(str(self.dc[i].components[k])))
                parent.setEditable(False)
                parent.setSelectable(False)
                
                child = QStandardItem('{}'.format('All data (' + self.dc.labels[i] + ')'))
                child.setIcon(helpers.layer_icon(self.dc[i]))
                child.setEditable(False)
                child.setIcon(helpers.layer_icon(self.dc[i]))
                    
                parent.appendRow(child)
                self.num_rows = self.num_rows + 1
                
                for j in range(0, len(self.dc.subset_groups)):
                    child = QStandardItem('{}'.format(self.dc.subset_groups[j].label))
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
                for j in range(0, grandparent.child(i).rowCount()):
                    if grandparent.child(i).child(j).row() == 0:
                        key = grandparent.child(i).child(j).text() + grandparent.child(i).text()
                        self.component_dict[key] = grandparent.child(i).child(j).index()
                    else:
                        key = grandparent.child(i).child(j).text() + " (" + grandparent.text() + ")" + grandparent.child(i).text()
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
            component = self.data_frame['Component'][i]
            dataset = self.data_frame['Dataset'][i]
            subset = self.data_frame['Subset'][i]
                
            # Pull the correct index of the data in data_accurate
            idx_c = np.where(component == self.data_accurate['Component'])
            idx_d = np.where(dataset == self.data_accurate['Dataset'])
            idx_s = np.where(subset == self.data_accurate['Subset'])
            idx1 = np.intersect1d(idx_c, idx_d)
            idx2 = np.intersect1d(idx1, idx_s)[0] 
                
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
      
    def updateStats(self, subset):
        print("table should be updated for subset ", subset)
    #     # For the subset that was updated:
    #     # Remove its rows from the table

        # Find the indices of that subset in the treeview and uncheck/recheck in treeview
        # myPressedEvent and run stats will handle the rest
        selected_items = []
        selected_names = []

        if self.component_mode:
            for i in range(0, len(self.selected_indices)):
                selected_items.append(self.model_components.itemFromIndex(self.selected_indices[i]))
                selected_names.append(selected_items[i].text())
            indices = np.asarray(np.where(selected_names == subset))[0]
            for i in range(0, len(indices)):
                self.model_components.itemFromIndex(indices[i]).setCheckState(Qt.Unchecked)
                self.model_components.itemFromIndex(indices[i]).setCheckState(Qt.Checked)
        else:
            for i in range(0, len(self.selected_indices)):
                selected_items.append(self.model_subsets.itemFromIndex(self.selected_indices[i]))
                selected_names.append(selected_items[i].parent().parent().text())
            indices = np.asarray(np.where(selected_names == subset))[0]
            for i in range(0, len(indices)):
                self.model_subsets.itemFromIndex(indices[i]).setCheckState(Qt.Unchecked)
                self.model_subsets.itemFromIndex(indices[i]).setCheckState(Qt.Checked)

    def messageReceived(self, message):
        self.no_update = False
        print("Message received:")
        print("{0}".format(message))

        if "Updated subset_state" in str(message):
            # Get the subset that was updated
            index1 = str(message).index("Sent from: Subset: ") + len("Sent from: Subset: ")
            index2 = str(message).index(" (data: ")
            subset_name = str(message)[index1:index2]
            self.updateStats(subset_name)  

        if self.component_mode:
            index_dict = self.component_dict

            # Save the selected rows from the component view
            try:
                selected = dict()
                for i in range(0, len(self.selected_indices)):
                    item = self.model_components.itemFromIndex(self.selected_indices[i])
                    if item.row() != 0:
                        key = item.text() + " (" + item.parent().parent().text() + ")"+ item.parent().text()
                        selected[key] = item.index()
                    else:
                        key = item.text() + item.parent().text()
                        selected[key] = item.index() 
            except:
                pass

            self.sortByComponents()

            #         # Select the correct rows 
            # for i in range(0, len(selected)):
            #     key = list(selected.keys())[i]
            #     index = self.index_dict[key]
            #     print(type(index))
            #     self.treeview.setCurrentIndex(index)

        else:
            index_dict = self.subset_dict

            # Save the selected rows from the subset view if applicable
            try:
                selected = dict()

                for i in range(0, len(self.selected_indices)):
                    item = self.model_subsets.itemFromIndex(self.selected_indices[i])
                    if item.parent().parent().text() == "Data":
                        key =  "All data (" + item.parent().text() + ")" + item.text()
                        selected[key] = item.index()
                    else:
                        key = item.parent().text() + item.text()
                        selected[key] = item.index()
            except:
                pass

            self.sortBySubsets()

        # Select the correct rows 
        for i in range(0, len(selected)):
            key = list(selected.keys())[i]
            index = index_dict[key]
            self.treeview.setCurrentIndex(index)


        # # BELOW CODE SHOULD BE ABLE TO REPLACE LINES 1003-1047

        # # Save the currently selected indices
        # selected = self.selected_indices

        # if self.component_mode:
        #     self.sortByComponents()

        # else:
        #     self.sortBySubsets()

        # for i in range(0, len(selected)):
        #     self.treeview.setCurrentIndex(selected[i])

        self.no_update = True


