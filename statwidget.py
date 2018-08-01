import pandas as pd

from  PyQt5.QtCore  import QAbstractItemModel, pyqtSignal, QSize, QFile, QIODevice, QModelIndex, Qt, pyqtSlot, QVariant, QItemSelectionModel
from PyQt5.QtWidgets import QSizePolicy, QTreeView, QAbstractScrollArea, QSpinBox, QToolButton, QHeaderView, QAbstractItemView, QApplication, QLabel, QTreeView, QComboBox, QCheckBox, QWidget, QPushButton, QHBoxLayout, QFrame, QTableView, QGroupBox, QDialog, QVBoxLayout, QLabel, QGridLayout
from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from decimal import getcontext, Decimal
from IPython.display import display, HTML
from PyQt5.QtGui import *
import sys
from qtpy import compat
from glue.icons.qt import helpers

class pandasModel(QtCore.QAbstractTableModel):
    # Set up the data in a form that allows it to be added to qt widget
    def __init__(self, df, dc, parent=None):
        QtCore.QAbstractTableModel.__init__(self, parent)
        self.dc = dc
        self.data_frame = df
        self.subset_labels = []
        
        # Create an array of subset labels
        for i in range(0, len(self.dc.subset_groups)):
            self.subset_labels.append(dc.subset_groups[i].label)
        
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
                    color = dc[data_index].subsets[subset_index].style.color
                    q_color = QColor(color)
                    rgb_color = q_color.getRgb()
                    
                    return QBrush(QColor(rgb_color[0], rgb_color[1], rgb_color[2], transparency))
                
                # If it is a dataset find the color and color accordingly 
                else:
                    color = dc[data_index].style.color
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
        
class StatsGui(QWidget):
    ''' 
    This class accepts a glue data collection object, and builds an interactive window
    to display basic statistics (e.g. mean, median, mode) about each dataset
    '''
    
    released = QtCore.pyqtSignal(object)
    
    def __init__(self,dc):
        
        # Initialize the object as a QWidget
        QWidget.__init__(self)
        
        #Save the datacollection object as an attribute of class StatsGui
        self.dc=dc
        
        #Set the title of the main GUI window
        self.setWindowTitle('Statistics')
        
        # Set up dicts for row indices
        self.subset_dict = dict()
        self.component_dict = dict()
        
        self.selected_dict = dict()
        self.selected_indices = []
        
        #Set up tree view and fix it to the top half of the window
        self.treeview = QTreeView(self)

        # Set the default clicking behavior to be row selection
        self.treeview.setSelectionBehavior(QAbstractItemView.SelectRows)
        
        # Set up expand all, collapse all, select all and deselect all buttons
        
        # Layout for expand/collapse/select/deselect
        layout_left_options = QHBoxLayout()
        
        self.expand_data = QToolButton(self)
        self.expand_data.setText("Expand all data and subsets")
        self.expand_data.clicked.connect(self.expandClicked)
        layout_left_options.addWidget(self.expand_data)
        
        self.all = QToolButton(self)
        self.all.setText('Select all')
        self.all.clicked.connect(self.allClicked)
        layout_left_options.addWidget(self.all)
        
        self.none = QToolButton(self)
        self.none.setText('Deselect all')
        self.none.clicked.connect(self.noneClicked)
        layout_left_options.addWidget(self.none)
        
        # Set default significant figures to 5
        getcontext().prec = 5
        
        # Set up past selected items
        self.past_selected = []
        
        # Sort by subsets as a default
        self.sortBySubsets()

        # Set up the combo box for users to choose the number of significant figures in the table
        
        # Set up bottom options layout
        layout_bottom_options = QHBoxLayout()
        
        self.siglabel = QLabel(self)
        self.siglabel.setText('Number of significant figures:')
        layout_bottom_options.addWidget(self.siglabel)
        
        self.sigfig = QSpinBox(self)
        self.sigfig.setRange(1,10)
        self.sigfig.setValue(5)
        self.sigfig.valueChanged.connect(self.sigchange)
        layout_bottom_options.addWidget(self.sigfig)
        
        # Export to file button
        self.export = QPushButton(self)
        self.export.setText('Export to file')
        self.export.clicked.connect(self.exportToFile)
        layout_bottom_options.addWidget(self.export)
        
        # Set up the toggle button to switch tree sorting modes
        self.switch_mode = QToolButton(self)
        self.switch_mode.setText('Sort tree by components')
        self.switch_mode.clicked.connect(self.switchMode)
        layout_left_options.addWidget(self.switch_mode)
        
        # Add instructions to sort the table
        self.how = QLabel(self)
        self.how.setText('Click each header to sort table')
        layout_left_options.addWidget(self.how)
                 
        #################Set up the QTableView Widget#############################
        self.table = QTableView(self)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        
        #Set the table headings
        self.headings = ('Subset', 'Dataset', 'Component','Mean', 'Median', 'Minimum', 'Maximum', 'Sum')   
        self.data_frame = pd.DataFrame(columns=self.headings) 
        self.data_accurate = pd.DataFrame(columns=self.headings)
        self.model = pandasModel(self.data_frame, self.dc)

        self.table.setModel(self.model) 
        
        layout_table = QHBoxLayout()
        layout_table.addWidget(self.table)
        layout_table.stretch(10)

        # Finish nesting all the layouts
        main_layout = QVBoxLayout()
        
        main_layout.addWidget(self.treeview)
        main_layout.addLayout(layout_left_options)
        main_layout.addLayout(layout_table)
        main_layout.addLayout(layout_bottom_options)
        
        self.setLayout(main_layout)
        
        # Set up dict for caching
        self.cache_stash = dict()
    
    def myPressedEvent (self, currentQModelIndex):
        ''' 
        Every time a row (or rows) in the tree view is clicked:
        if it is selected, add it to the table
        if it is deselected, remove it from the table
        ''' 
            
        # Get the indexes of all the selected components
        self.selected_indices = self.treeview.selectionModel().selectedRows()
        
        newly_selected = np.setdiff1d(self.selected_indices, self.past_selected)
            
        for index in range (0, len(newly_selected)):
                
            # Check which view mode the tree is in to get the correct indices
            if self.switch_mode.text() == 'Sort tree by components':
                data_i = newly_selected[index].parent().row()
                comp_i = newly_selected[index].row()
                subset_i = newly_selected[index].parent().parent().row()
            
            else:
                data_i = newly_selected[index].parent().parent().row()
                comp_i = newly_selected[index].parent().row()
                subset_i = newly_selected[index].row() - 1
    
            is_subset = newly_selected[index].parent().parent().parent().row() == 1 or (self.switch_mode.text() == 'Sort tree by subsets' and subset_i != -1)

            # Check if its a subset and if so run subset stats
            if is_subset:       
                self.runSubsetStats(subset_i, data_i, comp_i)
            else:
                # Run standard data stats
                self.runDataStats(data_i, comp_i)            
            
        newly_dropped = np.setdiff1d(self.past_selected, self.selected_indices)
            
        for index in range (0, len(newly_dropped)):
                
            # Check which view mode the tree is in to get the correct indices
            if self.switch_mode.text() == 'Sort tree by components':
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
        data_label = dc[data_i].label   
        comp_label = self.dc[data_i].components[comp_i].label # add to the name array to build the table
        
        # Build the cache key
        cache_key = subset_label + data_label + comp_label
        
        # See if the values have already been cached
        try:
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
        column_df = pd.DataFrame(column_data, columns = self.headings)
        self.data_accurate = self.data_accurate.append(column_df, ignore_index = True)        
        
        # Round the values according to the number of significant figures set by the user
        mean_val = Decimal(float(column_data[0][3])) * Decimal(1)
        median_val = Decimal(float(column_data[0][4])) * Decimal(1)
        min_val = Decimal(float(column_data[0][5])) * Decimal(1)
        max_val = Decimal(float(column_data[0][6])) * Decimal(1)
        sum_val = Decimal(float(column_data[0][7])) * Decimal(1)
        
        # Create the column data array and append it to the data frame
        column_data = np.asarray([[subset_label], [data_label], [comp_label], [mean_val], [median_val], [min_val], [max_val], [sum_val]]).transpose()
        column_df = pd.DataFrame(column_data, columns = self.headings)
        self.data_frame = self.data_frame.append(column_df, ignore_index = True)
    
    def runSubsetStats (self, subset_i, data_i, comp_i):
        '''
        Runs statistics for the subset subset_i with respect to the component comp_i of data set data_i
        '''

        subset_label = dc[data_i].subsets[subset_i].label
        data_label = dc[data_i].label   
        comp_label = self.dc[data_i].components[comp_i].label # add to the name array to build the table
        
        # Build the cache key
        cache_key = subset_label + data_label + comp_label
        
        # See if the statistics are already in the cache
        try:
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
        column_df = pd.DataFrame(column_data, columns = self.headings)
        self.data_accurate = self.data_accurate.append(column_df, ignore_index = True)        
        
        # Round the values according to the number of significant figures set by the user
        mean_val = Decimal(float(column_data[0][3])) * Decimal(1)
        median_val = Decimal(float(column_data[0][4])) * Decimal(1)
        min_val = Decimal(float(column_data[0][5])) * Decimal(1)
        max_val = Decimal(float(column_data[0][6])) * Decimal(1)
        sum_val = Decimal(float(column_data[0][7])) * Decimal(1)
        
        # Create the column data array and append it to the data frame
        column_data = np.asarray([[subset_label], [data_label], [comp_label], [mean_val], [median_val], [min_val], [max_val], [sum_val]]).transpose()
        column_df = pd.DataFrame(column_data, columns = self.headings)
        self.data_frame = self.data_frame.append(column_df, ignore_index = True)    
    
    def sigchange(self, i):
        # Set the number of significant figures according to what the user selects
        getcontext().prec = i
        
        # Retrospectively change the number of significant figures in the table
        
        data_labels = self.data_frame['Dataset']
        comp_labels = self.data_frame['Component']
        subset_labels = self.data_frame['Subset']
        
        mean_vals = []
        median_vals = []
        min_vals = []
        max_vals = []
        sum_vals = []
        
        # Get the values from the self.data_accurate array and append them
        for i in range (0, len(self.data_frame)):
            mean_vals.append(Decimal(self.data_accurate['Mean'][i]) * Decimal(1))
            median_vals.append(Decimal(self.data_accurate['Median'][i]) * Decimal(1))
            min_vals.append(Decimal(self.data_accurate['Minimum'][i]) * Decimal(1))
            max_vals.append(Decimal(self.data_accurate['Maximum'][i]) * Decimal(1))
            sum_vals.append(Decimal(self.data_accurate['Sum'][i]) * Decimal(1))
            
        column_data = np.asarray([subset_labels, data_labels, comp_labels, mean_vals, median_vals, min_vals, max_vals, sum_vals]).transpose()
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
        
    def allClicked(self):
        # Select all components of the treeview if checked and fill the table with newly checked items
        # Does not deselect if user unclicks it
        
        original_idx = self.treeview.selectionModel().selectedRows()

        self.treeview.selectAll()
        end_idx=self.treeview.selectionModel().selectedRows()
        for index in end_idx:
            if index not in original_idx:
                # Check to see if the clicked item is a subset component or a data component
                if index.parent().parent().parent().row() != 1:
                    self.runDataStats(index.parent().row(), index.row())
                else:
                    self.runSubsetStats(index.parent().parent().row(), index.parent().row(), index.row())
        
        # Set the table to display the correct data frame
        model = pandasModel(self.data_frame, self.dc)
        self.table.setModel(model)
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False) 

    def noneClicked(self):
        self.treeview.clearSelection()
        self.data_frame = pd.DataFrame(columns = self.headings)
        model = pandasModel(self.data_frame, self.dc)
        self.table.setModel(model)
        self.table.setSortingEnabled(True)
        self.table.setShowGrid(False)
        
    def exportToFile(self):
        file_name,fltr=compat.getsavefilename(caption="Choose an output filename")
        
        try:
            self.data_frame.to_csv(str(file_name), index=False)
        except:
            print("passed")
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
  
    def sizeHint(self):
        return QSize(600, 800)
    
    def sortBySubsets(self):
        '''
        Sorts the treeview by subsets- Dataset then subset then component.
        What we originally had as the default
        '''
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
        
        # Set Expand/collapse button to "expand all"
        self.expand_data.setText("Expand all data and subsets")       
        
        #Allow the user to select multiple rows at a time 
        self.selection_model = QAbstractItemView.MultiSelection
        self.treeview.setSelectionMode(self.selection_model)
        
        # See if the model already exists instead of regenerating
        try:
            self.treeview.setModel(self.model_subsets)
        
        except:
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
                    child=QStandardItem('{}'.format(str(self.dc[i].components[j])))
                    child.setEditable(False)
                    
                    # Add to the subset_dict
                    key = self.dc[i].label + self.dc[i].components[j].label + "All data-" + self.dc[i].label
                    self.subset_dict[key] = child.index()
                    
                    parent.appendRow(child)

                parent_data.appendRow(parent)

                #Add the parents with their children to the QStandardItemModel
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
                        
                        # Update the dict to keep track of row indices
                        key = self.dc[i].label + self.dc[i].components[k].label + self.dc[i].subsets[j].label
                        self.subset_dict[key] = child.index()
                        
                        parent.appendRow(child)

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
        
        self.treeview.setUniformRowHeights(True)
        
        selection_model = QItemSelectionModel(self.model_subsets)
        self.treeview.setSelectionModel(selection_model)
        selection_model.selectionChanged.connect(self.myPressedEvent)

        # Select rows that should be selected
        
        sel_mod = self.treeview.selectionModel()
        
        for i in range(0, len(selected)):
#             key = list(self.selected_dict.keys())[list(self.selected_dict.values()).index(self.selected_dict[i])]
            key = list(selected.keys())[i]
            index = self.subset_dict[key]
            print(index.parent().row(), index.row())
#             print(index, type(index))
#             print(type(self.treeview.selectionModel().select(index, QItemSelectionModel.Select)))
#             sel_mod.select(index, QItemSelectionModel.Select|QItemSelectionModel.Rows)
            self.treeview.setCurrentIndex(index)
    
        self.treeview.setSelectionModel(sel_mod)
    
    def sortByComponents(self):
        '''
        Sorts the treeview by components- Dataset then component then subsets
        '''      
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
        
        # Set Expand/collapse button to "expand all"
        self.expand_data.setText("Expand all data and subsets")
        
        self.selection_model = QAbstractItemView.MultiSelection
        self.treeview.setSelectionMode(self.selection_model)
        
        # See if the model already exists
        try:
            self.treeview.setModel(self.model_components)
            
        except: 
        
            self.model_components = QStandardItemModel()
            self.model_components.setHorizontalHeaderLabels([''])

            self.treeview.setModel(self.model_components)
            self.treeview.setUniformRowHeights(True)
    
            # populate the tree
            # Make all the datasets be parents, and make it so they are not selectable
        
            for i in range(0,len(dc)):
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
                    
                    parent.appendRow(child)
                
                    for j in range(0, len(self.dc.subset_groups)):
                        child = QStandardItem('{}'.format(self.dc.subset_groups[j].label))
                        child.setEditable(False)
                        child.setIcon(helpers.layer_icon(self.dc.subset_groups[j]))
                        
                        try:
                            self.dc[i].compute_statistic('mean', self.dc[i].subsets[j].components[k], subset_state=self.dc[i].subsets[j].subset_state)

                        except:
#                             print("Glue has raised an Incompatible Attribute error on this component. Let's do this instead.")
                            child.setEditable(False)
                            child.setSelectable(False)
                            child.setForeground(QtGui.QBrush(Qt.gray)) 

                        parent.appendRow(child)
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
            
        self.treeview.setUniformRowHeights(True)
        
        selection_model = QItemSelectionModel(self.model_components)
        self.treeview.setSelectionModel(selection_model)
        selection_model.selectionChanged.connect(self.myPressedEvent)
 
        # Select the rows that should be selected

        sel_mod = self.treeview.selectionModel()
    
        for i in range(0, len(selected)):
            key = list(selected.keys())[i]
            index = self.component_dict[key]
#             self.treeview.selectionModel().select(index, QItemSelectionModel.Select)
            print(index.parent().row(), index.row())
            # This causes an error when it runs
#             sel_mod.select(index, QItemSelectionModel.Select|QItemSelectionModel.Rows)
            self.treeview.setCurrentIndex(index)

        self.treeview.setSelectionModel(sel_mod)


if __name__ == '__main__':
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    else:
        print('QApplication instance already exists: %s' % str(app))
    ex = StatsGui(dc)
    ex.show()
    sys.exit(app.exec_())
