from django_components import Component


class Page(Component):
    template_name = "page/page.html"

    class Media:
        pass

    def get_context_data(self, title="", back_hx_get="", back_hx_target="", back_hx_push_url=""):
        return {
            "title": title,
            "back_hx_get": back_hx_get,
            "back_hx_target": back_hx_target,
            "back_hx_push_url": back_hx_push_url,
        }
