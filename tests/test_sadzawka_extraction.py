"""Offline regression tests for Sadzawka labelled botanical attributes."""
import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/collect_sadzawka_catalog.py"
spec = importlib.util.spec_from_file_location("sadzawka_collector", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

SAMPLE = """<html><body><div class="product-description">
<h3>Opis</h3>
<p>Geranium wallichianum „Kelly-Anne” - bodziszek</p>
<p>rodzina: Geraniaceae<br>hodowca: Molter B.V.<br>
stanowisko: słoneczne, półcieniste<br>
wysokość: do 35 cm (w czasie kwitnienia)<br>
kwitnienie: V-XI</p>
<p>Ten niski bodziszek o różowych kwiatach to bylina. Kwitnie długo i jest mrozoodporny.</p>
<p>Rośnie w doniczce p11.</p>
<h3>Opinie (0)</h3></div></body></html>"""

class ExtractorTests(unittest.TestCase):
    def test_botanical_fields_and_description(self):
        traits, desc = mod.botanical_text(SAMPLE, 'Geranium wallichianum Kelly-Anne')
        self.assertEqual(traits["family"], "Geraniaceae")
        self.assertEqual(traits["light"], "солнце или полутень")
        self.assertEqual(traits["height_cm_max"], 35)
        self.assertEqual(traits["flowering"], "май — ноябрь")
        self.assertNotIn("breeder", traits)
        self.assertNotIn("container_at_sale", traits)
        self.assertNotIn("p11", desc.lower())
    def test_no_invented_values(self):
        traits, _ = mod.botanical_text(SAMPLE, 'Geranium wallichianum Kelly-Anne')
        self.assertNotIn("soil", traits)
        self.assertNotIn("moisture", traits)
        self.assertNotIn("width_cm_max", traits)
    def test_polish_first_paragraph_preserved(self):
        traits, desc = mod.botanical_text(SAMPLE, 'Geranium wallichianum Kelly-Anne')
        self.assertEqual(desc, "Ten niski bodziszek o różowych kwiatach to bylina. Kwitnie długo i jest mrozoodporny.")
        self.assertNotIn("hodowca", desc.lower())
    def test_paragraph_without_labelled_fields(self):
        raw = '<div><p>Hosta Blue Mouse Ears</p><p>Ta niewielka roślina o niebieskawych liściach tworzy gęste kępy w ogrodzie.</p></div>'
        traits, desc = mod.botanical_text(raw, 'Hosta Blue Mouse Ears')
        self.assertEqual(traits, {})
        self.assertTrue(desc.startswith('Ta niewielka roślina'))
    def test_retail_paragraph_skipped(self):
        raw = '<p>Roślina dostępna w doniczce P11, dodaj do koszyka i zamów.</p><p>Ta piękna bylina kwitnie długo w ogrodzie i tworzy szerokie kępy.</p>'
        self.assertIn('bylina', mod.botanical_text(raw, 'Plant')[1])
        self.assertNotIn('P11', mod.botanical_text(raw, 'Plant')[1])
    def test_real_page_combined_specification_is_not_description(self):
        # Live Sadzawka page concatenates labels in one <p>, without spacing.
        raw = ('<p>Geranium wallichianum „Kelly-Anne” - bodziszek '
               'rodzina: Geraniaceaehodowca: Molter B.V. stanowisko: słoneczne, półcieniste '
               'wysokość: do 35 cm (w czasie kwitnienia) kwitnienie: V-XI</p>'
               '<p>Ta niska bylina kwitnie pięknymi kwiatami od maja aż do jesieni w ogrodzie.</p>')
        traits, desc = mod.botanical_text(raw, 'Geranium wallichianum Kelly-Anne')
        self.assertEqual(desc, 'Ta niska bylina kwitnie pięknymi kwiatami od maja aż do jesieni w ogrodzie.')
        self.assertNotIn('hodowca:', desc)
        self.assertNotIn('rodzina:', desc)
    def test_meters_conversion(self):
        self.assertEqual(mod.convert_field("height_cm_max", "1,2 m"), 120)
        self.assertEqual(mod.convert_field("width_cm_max", "45 cm"), 45)

if __name__ == "__main__":
    unittest.main()
