from enum import Enum


class By(Enum):
    """Strategy for locating widgets in a UI hierarchy dump.

    Attributes:
        TEXT: Match by visible text content.
        XPATH: Match by XPath expression.
        CLASS: Match by Android class name.
        ID: Match by resource-id.
        CONTENT_DESC: Match by content-description (accessibility).
        WIDGET: Special marker for raw widget matching.
    """

    TEXT = "text"
    XPATH = "xpath"
    CLASS = "class_name"
    ID = "id"
    CONTENT_DESC = "content_desc"
    WIDGET = "widget"
