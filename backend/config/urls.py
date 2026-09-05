from apps.core import views as v
from apps.core.schema import install_schema
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

install_schema()

urlpatterns = [
    path("api/v1/schema", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs", SpectacularSwaggerView.as_view(url_name="schema")),
]
routes = [
    ("health/live", v.LiveView),
    ("health/ready", v.ReadyView),
    ("session", v.SessionView),
    ("capabilities", v.CapabilitiesView),
    ("regions", v.RegionsView),
    ("regions/<uuid:id>", v.RegionView),
    ("polygons", v.PolygonsView),
    ("polygons/<uuid:id>", v.PolygonView),
    ("polygons/<uuid:id>/analyses", v.PolygonAnalysesView),
    ("analyses", v.AnalysesView),
    ("analyses/<uuid:id>", v.AnalysisView),
    ("analyses/<uuid:id>/series", v.SeriesView),
    ("analyses/<uuid:id>/anomalies", v.AnomaliesView),
    ("analyses/<uuid:id>/quality", v.QualityView),
    ("jobs/<uuid:id>", v.JobView),
    ("jobs/<uuid:id>/cancel", v.CancelView),
    ("jobs/<uuid:id>/retry", v.RetryView),
    ("discoveries", v.DiscoveriesView),
    ("discoveries/<uuid:id>", v.DiscoveryView),
    ("exports", v.ExportsView),
    ("exports/<uuid:id>", v.ExportView),
    ("exports/<uuid:id>/download", v.DownloadView),
    ("exports/<uuid:id>/manifest", v.ExportManifestView),
    ("models", v.ModelsView),
    ("comparisons", v.ComparisonsView),
]
urlpatterns += [path("api/v1/" + route, view.as_view()) for route, view in routes]
