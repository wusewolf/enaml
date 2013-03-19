#------------------------------------------------------------------------------
# Copyright (c) 2013, Nucleic Development Team.
#
# Distributed under the terms of the Modified BSD License.
#
# The full license is in the file COPYING.txt, distributed with this software.
#------------------------------------------------------------------------------
from collections import deque

import wx

from atom.api import Bool, List, Callable, Value, Typed

from casuarius import weak

from enaml.layout.layout_manager import LayoutManager
from enaml.widgets.container import ProxyContainer

from .wx_constraints_widget import WxConstraintsWidget, size_hint_guard


class wxContainer(wx.PyPanel):
    """ A subclass of wx.PyPanel which allows the default best size to
    be overriden by calling SetBestSize.

    This functionality is used by the WxContainer to override the
    size hint with a value computed from the constraints layout
    manager.

    """
    #: An invalid wx.Size used as the default value for class instances.
    _best_size = wx.Size(-1, -1)

    def DoGetBestSize(self):
        """ Reimplemented parent class method.

        This will return the best size as set by a call to SetBestSize.
        If that is invalid, then the superclass' version will be used.

        """
        size = self._best_size
        if not size.IsFullySpecified():
            size = super(wxContainer, self).DoGetBestSize()
        return size

    def SetBestSize(self, size):
        """ Sets the best size to use for this container.

        """
        self._best_size = size


class WxContainer(WxConstraintsWidget, ProxyContainer):
    """ A Wx implementation of an Enaml ProxyContainer.

    """
    #: A reference to the toolkit widget created by the proxy.
    widget = Typed(wxContainer)

    #: A list of the contents constraints for the widget.
    contents_cns = List()

    #: Whether or not this container owns its layout. A container which
    #: does not own its layout is not responsible for laying out its
    #: children on a resize event, and will proxy the call to its owner.
    _owns_layout = Bool(True)

    #: The object which has taken ownership of the layout for this
    #: container, if any.
    _layout_owner = Value()

    #: The LayoutManager instance to use for solving the layout system
    #: for this container.
    _layout_manager = Value()

    #: The function to use for refreshing the layout on a resize event.
    _refresh = Callable(lambda *args, **kwargs: None)

    #: The table of offsets to use during a layout pass.
    _offset_table = List()

    #: The table of (index, updater) pairs to use during a layout pass.
    _layout_table = List()

    #: Whether or not the current container is shown. This is toggled
    #: by the EVT_SHOW handler.
    _is_shown = Bool(True)

    def _default_contents_cns(self):
        """ Create the contents constraints for the container.

        The contents contraints are generated by combining the user
        padding with the margins returned by 'contents_margins' method.

        Returns
        -------
        result : list
            The list of casuarius constraints for the content.

        """
        d = self.declaration
        margins = self.contents_margins()
        top, right, bottom, left = map(sum, zip(d.padding, margins))
        cns = [
            d.contents_top == (d.top + top),
            d.contents_left == (d.left + left),
            d.contents_right == (d.left + d.width - right),
            d.contents_bottom == (d.top + d.height - bottom),
        ]
        return cns

    #--------------------------------------------------------------------------
    # Initialization API
    #--------------------------------------------------------------------------
    def create_widget(self):
        """ Creates the QContainer widget.

        """
        self.widget = wxContainer(self.parent_widget())

    def init_widget(self):
        """ Initialize the widget.

        """
        super(WxContainer, self).init_widget()
        widget = self.widget
        widget.Bind(wx.EVT_SIZE, self.on_resized)
        widget.Bind(wx.EVT_SHOW, self.on_shown)

    def init_layout(self):
        """ Initialize the layout of the widget.

        """
        super(WxContainer, self).init_layout()
        self.init_cns_layout()

    def init_cns_layout(self):
        """ Initialize the constraints layout.

        """
        # Layout ownership can only be transferred *after* this init
        # layout method is called, since layout occurs bottom up. So,
        # we only initialize a layout manager if ownership is unlikely
        # to be transferred.
        if not self.will_transfer():
            offset_table, layout_table = self._build_layout_table()
            cns = self._generate_constraints(layout_table)
            manager = LayoutManager()
            manager.initialize(cns)
            self._offset_table = offset_table
            self._layout_table = layout_table
            self._layout_manager = manager
            self._refresh = self._build_refresher(manager)
            self._update_sizes()

    #--------------------------------------------------------------------------
    # Event Handlers
    #--------------------------------------------------------------------------
    def on_resized(self, event):
        """ Update the position of the widgets in the layout.

        This makes a layout pass over the descendents if this widget
        owns the responsibility for their layout.

        """
        # The _refresh function is generated on every relayout and has
        # already taken into account whether or not the container owns
        # the layout.
        if self._is_shown:
            self._refresh()

    def on_shown(self, event):
        """ The event handler for the EVT_SHOW event.

        This handler toggles the value of the _is_shown flag.

        """
        # The EVT_SHOW event is not reliable. For example, it is not
        # emitted on the children of widgets that were hidden. So, if
        # this container is the child of, say, a notebook page, then
        # the switching of tabs does not emit a show event. So, the
        # notebook page must cooperatively emit a show event on this
        # container. Therefore, we can't treat this event as a 'real'
        # toolkit event, we just use it as a hint.
        self._is_shown = shown = event.GetShow()
        if shown:
            self._refresh()

    #--------------------------------------------------------------------------
    # Public Layout Handling
    #--------------------------------------------------------------------------
    def relayout(self):
        """ Rebuild the constraints layout for the widget.

        If this object does not own the layout, the call is proxied to
        the layout owner.

        """
        if self._owns_layout:
            widget = self.widget
            old_hint = widget.GetBestSize()
            self.init_cns_layout()
            if self._is_shown:
                self._refresh()
            new_hint = widget.GetBestSize()
            # If the size hint constraints are empty, it indicates that
            # they were previously cleared. In this case, the layout
            # system must be notified to rebuild its constraints, even
            # if the numeric size hint hasn't changed.
            if old_hint != new_hint or not self.size_hint_cns:
                self.size_hint_updated()
        else:
            self._layout_owner.relayout()

    def replace_constraints(self, old_cns, new_cns):
        """ Replace constraints in the given layout.

        This method can be used to selectively add/remove/replace
        constraints in the layout system, when it is more efficient
        than performing a full relayout.

        Parameters
        ----------
        old_cns : list
            The list of casuarius constraints to remove from the
            the current layout system.

        new_cns : list
            The list of casuarius constraints to add to the
            current layout system.

        """
        if self._owns_layout:
            manager = self._layout_manager
            if manager is not None:
                with size_hint_guard(self):
                    manager.replace_constraints(old_cns, new_cns)
                    self._update_sizes()
                    if self._is_shown:
                        self._refresh()
        else:
            self._layout_owner.replace_constraints(old_cns, new_cns)

    def clear_constraints(self, cns):
        """ Clear the given constraints from the current layout.

        Parameters
        ----------
        cns : list
            The list of casuarius constraints to remove from the
            current layout system.

        """
        if self._owns_layout:
            manager = self._layout_manager
            if manager is not None:
                manager.replace_constraints(cns, [])
        else:
            self._layout_owner.clear_constraints(cns)

    def contents_margins(self):
        """ Get the contents margins for the container.

        The contents margins are added to the user provided padding
        to determine the final offset from a layout box boundary to
        the corresponding content line. The default content margins
        are zero. This method can be reimplemented by subclasses to
        supply different margins.

        Returns
        -------
        result : tuple
            A tuple of 'top', 'right', 'bottom', 'left' contents
            margins to use for computing the contents constraints.

        """
        return (0, 0, 0, 0)

    def contents_margins_updated(self):
        """ Notify the system that the contents margins have changed.

        """
        old_cns = self.contents_cns
        del self.contents_cns
        new_cns = self.contents_cns
        self.replace_constraints(old_cns, new_cns)

    #--------------------------------------------------------------------------
    # Private Layout Handling
    #--------------------------------------------------------------------------
    def _layout(self):
        """ The layout callback invoked by the layout manager.

        This iterates over the layout table and calls the geometry
        updater functions.

        """
        # We explicitly don't use enumerate() to generate the running
        # index because this method is on the code path of the resize
        # event and hence called *often*. The entire code path for a
        # resize event is micro optimized and justified with profiling.
        offset_table = self._offset_table
        layout_table = self._layout_table
        running_index = 1
        for offset_index, updater in layout_table:
            dx, dy = offset_table[offset_index]
            new_offset = updater(dx, dy)
            offset_table[running_index] = new_offset
            running_index += 1

    def _update_sizes(self):
        """ Update the min/max/best sizes for the underlying widget.

        This method is called automatically at the proper times. It
        should not normally need to be called by user code.

        """
        widget = self.widget
        widget.SetBestSize(self.compute_best_size())
        widget.SetMinSize(self.compute_min_size())
        widget.SetMaxSize(self.compute_max_size())

    def _build_refresher(self, manager):
        """ Build the refresh function for the container.

        Parameters
        ----------
        manager : LayoutManager
            The layout manager to use when refreshing the layout.

        """
        # The return function is a hyper optimized (for Python) closure
        # in order minimize the amount of work which is performed on the
        # code path of the resize event. This is explicitly not idiomatic
        # Python code. It exists purely for the sake of efficiency,
        # justified with profiling.
        mgr_layout = manager.layout
        d = self.declaration
        layout = self._layout
        width_var = d.width
        height_var = d.height
        size = self.widget.GetSizeTuple
        return lambda: mgr_layout(layout, width_var, height_var, size())

    def _build_layout_table(self):
        """ Build the layout table for this container.

        A layout table is a pair of flat lists which hold the required
        objects for laying out the child widgets of this container.
        The flat table is built in advance (and rebuilt if and when
        the tree structure changes) so that it's not necessary to
        perform an expensive tree traversal to layout the children
        on every resize event.

        Returns
        -------
        result : (list, list)
            The offset table and layout table to use during a resize
            event.

        """
        # The offset table is a list of (dx, dy) tuples which are the
        # x, y offsets of children expressed in the coordinates of the
        # layout owner container. This owner container may be different
        # from the parent of the widget, and so the delta offset must
        # be subtracted from the computed geometry values during layout.
        # The offset table is updated during a layout pass in breadth
        # first order.
        #
        # The layout table is a flat list of (idx, updater) tuples. The
        # idx is an index into the offset table where the given child
        # can find the offset to use for its layout. The updater is a
        # callable provided by the widget which accepts the dx, dy
        # offset and will update the layout geometry of the widget.
        zero_offset = (0, 0)
        offset_table = [zero_offset]
        layout_table = []
        queue = deque((0, child) for child in self.children())

        # Micro-optimization: pre-fetch bound methods and store globals
        # as locals. This method is not on the code path of a resize
        # event, but it is on the code path of a relayout. If there
        # are many children, the queue could potentially grow large.
        push_offset = offset_table.append
        push_item = layout_table.append
        push = queue.append
        pop = queue.popleft
        WxConstraintsWidget_ = WxConstraintsWidget
        WxContainer_ = WxContainer
        isinst = isinstance

        # The queue yields the items in the tree in breadth-first order
        # starting with the immediate children of this container. If a
        # given child is a container that will share its layout, then
        # the children of that container are added to the queue to be
        # added to the layout table.
        running_index = 0
        while queue:
            offset_index, item = pop()
            if isinst(item, WxConstraintsWidget_):
                push_item((offset_index, item.geometry_updater()))
                push_offset(zero_offset)
                running_index += 1
                if isinst(item, WxContainer_):
                    if item.transfer_layout_ownership(self):
                        for child in item.children():
                            push((running_index, child))

        return offset_table, layout_table

    def _generate_constraints(self, layout_table):
        """ Creates the list of casuarius LinearConstraint objects for
        the widgets for which this container owns the layout.

        This method walks over the items in the given layout table and
        aggregates their constraints into a single list of casuarius
        LinearConstraint objects which can be given to the layout
        manager.

        Parameters
        ----------
        layout_table : list
            The layout table created by a call to _build_layout_table.

        Returns
        -------
        result : list
            The list of casuarius LinearConstraints instances to pass to
            the layout manager.

        """
        # The list of raw casuarius constraints which will be returned
        # from this method to be added to the casuarius solver.
        cns = self.contents_cns[:]
        cns.extend(self.declaration._hard_constraints())
        cns.extend(self.declaration._collect_constraints())

        # The first element in a layout table item is its offset index
        # which is not relevant to constraints generation.
        for _, updater in layout_table:
            child = updater.item
            d = child.declaration
            cns.extend(d._hard_constraints())
            if isinstance(child, WxContainer):
                if child.transfer_layout_ownership(self):
                    cns.extend(d._collect_constraints())
                    cns.extend(child.contents_cns)
                else:
                    cns.extend(child.size_hint_cns)
            else:
                cns.extend(d._collect_constraints())
                cns.extend(child.size_hint_cns)

        return cns

    #--------------------------------------------------------------------------
    # Auxiliary Methods
    #--------------------------------------------------------------------------
    def transfer_layout_ownership(self, owner):
        """ A method which can be called by other components in the
        hierarchy to gain ownership responsibility for the layout
        of the children of this container. By default, the transfer
        is allowed and is the mechanism which allows constraints to
        cross widget boundaries. Subclasses should reimplement this
        method if different behavior is desired.

        Parameters
        ----------
        owner : Declarative
            The component which has taken ownership responsibility
            for laying out the children of this component. All
            relayout and refresh requests will be forwarded to this
            component.

        Returns
        -------
        results : bool
            True if the transfer was allowed, False otherwise.

        """
        if not self.declaration.share_layout:
            return False
        self._owns_layout = False
        self._layout_owner = owner
        del self._layout_manager
        del self._refresh
        del self._offset_table
        del self._layout_table
        return True

    def will_transfer(self):
        """ Whether or not the container expects to transfer its layout
        ownership to its parent.

        This method is predictive in nature and exists so that layout
        managers are not senslessly created during the bottom-up layout
        initialization pass. It is declared public so that subclasses
        can override the behavior if necessary.

        """
        d = self.declaration
        return d.share_layout and isinstance(self.parent(), WxContainer)

    def compute_min_size(self):
        """ Calculates the minimum size of the container which would
        allow all constraints to be satisfied.

        If the container's resist properties have a strength less than
        'medium', the returned size will be zero. If the container does
        not own its layout, the returned size will be invalid.

        Returns
        -------
        result : wxSize
            A (potentially invalid) wxSize which is the minimum size
            required to satisfy all constraints.

        """
        d = self.declaration
        shrink = ('ignore', 'weak')
        if d.resist_width in shrink and d.resist_height in shrink:
            return wx.Size(0, 0)
        if self._owns_layout and self._layout_manager is not None:
            w, h = self._layout_manager.get_min_size(d.width, d.height)
            if d.resist_width in shrink:
                w = 0
            if d.resist_height in shrink:
                h = 0
            return wx.Size(w, h)
        return wx.Size(-1, -1)

    def compute_best_size(self):
        """ Calculates the best size of the container.

        The best size of the container is obtained by computing the min
        size of the layout using a strength which is much weaker than a
        normal resize. This takes into account the size of any widgets
        which have their resist clip property set to 'weak' while still
        allowing the window to be resized smaller by the user. If the
        container does not own its layout, the returned size will be
        invalid.

        Returns
        -------
        result : wxSize
            A (potentially invalid) wxSize which is the best size that
            will satisfy all constraints.

        """
        if self._owns_layout and self._layout_manager is not None:
            d = self.declaration
            w, h = self._layout_manager.get_min_size(d.width, d.height, weak)
            return wx.Size(w, h)
        return wx.Size(-1, -1)

    def compute_max_size(self):
        """ Calculates the maximum size of the container which would
        allow all constraints to be satisfied.

        If the container's hug properties have a strength less than
        'medium', or if the container does not own its layout, the
        returned size will be invalid.

        Returns
        -------
        result : wxSize
            A (potentially invalid) wxSize which is the maximum size
            allowable while still satisfying all constraints.

        """
        d = self.declaration
        expanding = ('ignore', 'weak')
        if d.hug_width in expanding and d.hug_height in expanding:
            return wx.Size(-1, -1)
        if self._owns_layout and self._layout_manager is not None:
            w, h = self._layout_manager.get_max_size(d.width, d.height)
            if w < 0 or d.hug_width in expanding:
                w = -1
            if h < 0 or d.hug_height in expanding:
                h = -1
            return wx.Size(w, h)
        return wx.Size(-1, -1)
