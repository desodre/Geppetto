from __future__ import annotations

from enum import Enum


class CommonClasses(str, Enum):
    """Common Android class names used in UI hierarchies.

    Attributes:
        VIEW: The base class for all UI components.
        VIEW_GROUP: A container that can hold other views (e.g., LinearLayout).
        TEXT_VIEW: A view that displays text to the user.
        IMAGE_VIEW: A view that displays an image.
        BUTTON: A view that can be clicked to perform an action.
        LINEAR_LAYOUT: A view group that arranges its children in a single column or row.
        RELATIVE_LAYOUT: A view group that arranges its children relative to each other.
        FRAME_LAYOUT: A view group that displays a single child view.
        SCROLL_VIEW: A view group that allows scrolling of its child views.
        RECYCLER_VIEW: A view group that displays a list of items and recycles views for efficiency.
        LIST_VIEW: A view group that displays a list of items.
        EDIT_TEXT: A view that allows the user to enter and edit text.
        CHECK_BOX: A view that represents a checkbox that can be checked or unchecked.
        RADIO_BUTTON: A view that represents a radio button that can be selected or deselected.
        SWITCH: A view that represents a switch that can be toggled on or off.
        PROGRESS_BAR: A view that represents a progress bar that can show progress of an operation.
        IMAGE_BUTTON: A view that represents a button with an image instead of text.
        VIEW_PAGER: A view group that allows the user to flip left and right through pages of data.
    """

    VIEW = "android.view.View"
    VIEW_GROUP = "android.view.ViewGroup"
    TEXT_VIEW = "android.widget.TextView"
    IMAGE_VIEW = "android.widget.ImageView"
    BUTTON = "android.widget.Button"
    LINEAR_LAYOUT = "android.widget.LinearLayout"
    RELATIVE_LAYOUT = "android.widget.RelativeLayout"
    FRAME_LAYOUT = "android.widget.FrameLayout"
    SCROLL_VIEW = "android.widget.ScrollView"
    RECYCLER_VIEW = "androidx.recyclerview.widget.RecyclerView"
    LIST_VIEW = "android.widget.ListView"
    EDIT_TEXT = "android.widget.EditText"
    CHECK_BOX = "android.widget.CheckBox"
    RADIO_BUTTON = "android.widget.RadioButton"
    SWITCH = "android.widget.Switch"
    PROGRESS_BAR = "android.widget.ProgressBar"
    IMAGE_BUTTON = "android.widget.ImageButton"
    VIEW_PAGER = "androidx.viewpager.widget.ViewPager"
