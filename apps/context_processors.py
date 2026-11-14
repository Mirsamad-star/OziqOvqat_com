from .i18n_data import get_t

def language(request):
    """Faqat o‘zbek — til tugmalari o‘chirilgan."""
    return {
        "LANG": "uz",
        "T": get_t("uz"),
    }
