"""QGIS entry point for Tanzania Boundary Search."""


def classFactory(iface):  # pylint: disable=invalid-name
    """Return the plugin instance expected by QGIS."""
    from .tanzania_boundary_search import TanzaniaBoundarySearch

    return TanzaniaBoundarySearch(iface)
