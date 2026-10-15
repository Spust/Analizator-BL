import re
import pandas as pd
import requests
import streamlit as st

# Konfiguracja strony
st.set_page_config(
    page_title="BrickLink do Allegro - Analizator", page_icon="🧱", layout="wide"
)

st.title("🧱 BrickLink do Allegro - Analizator Nowych Zestawów")
st.markdown(
    "Wklej tekst ze sklepu BrickLink. Program odfiltruje nowe zestawy i"
    " automatycznie odrzuci figurki oraz kolekcje (Collectible/Collectibles)."
)

# 1. Inicjalizacja stanów sesji
if "input_text" not in st.session_state:
  st.session_state["input_text"] = ""

if "clear_pending" not in st.session_state:
  st.session_state["clear_pending"] = False

if "results_df" not in st.session_state:
  st.session_state["results_df"] = None

if "success_msg" not in st.session_state:
  st.session_state["success_msg"] = ""

# 2. Bezpieczne czyszczenie stanu PRZED utworzeniem widgetu tekstowego
if st.session_state["clear_pending"]:
  st.session_state["input_text"] = ""
  st.session_state["clear_pending"] = False

# Główne pole tekstowe powiązane ze stanem sesji
raw_text = st.text_area(
    "1. Wklej skopiowany tekst ze strony BrickLink:",
    height=250,
    placeholder=(
        "Wklej tutaj surowy tekst skopiowany ze strony sklepu..."
    ),
    key="input_text",
)


# Funkcja pobierająca aktualną cenę z API Promoklocki
def get_promoklocki_price(set_clean_num):
  try:
    url = f"https://api.promoklocki.pl/price/{set_clean_num}"
    response = requests.get(url, timeout=3)
    if response.status_code == 200:
      data = response.json()
      if isinstance(data, (int, float)):
        return float(data)
      elif isinstance(data, dict) and "price" in data:
        return float(data["price"])
      elif isinstance(data, str):
        return float(data)
  except Exception:
    pass
  return 0.0


if st.button("🚀 Analizuj oferty i zysk", type="primary"):
  if not raw_text.strip():
    st.warning("Najpierw wklej tekst ze strony BrickLinka!")
  else:
    blocks = raw_text.split("Add to Cart")
    matches = []

    for block in blocks:
      # Interesują nas tylko oferty "New" (i bez słowa "Used")
      if "New" in block and "Used" not in block:
        # ODRZUCANIE FIGUREK I KOLEKCJONERSKICH (CMF / Collectibles / F1 Race Cars itp.)
        if (
            "Collectible" in block
            or "Collectibles" in block
            or "Series" in block
            or "col" in block.lower()
        ):
          continue  # Pomijamy tę ofertę

        # 1. Szukamy ceny w PLN (obsługa przecinków w tysiącach np. 7,417.46)
        pln_match = re.search(r"~PLN\s*([\d,\.]+)", block)
        # 2. Szukamy numeru zestawu (np. 41368-1)
        set_match = re.search(r"([A-Za-z0-9\-]+\d-\d)", block)

        if pln_match and set_match:
          raw_price_str = pln_match.group(1).replace(",", "")
          try:
            bl_pln_price = float(raw_price_str)
          except ValueError:
            continue

          raw_set_str = set_match.group(1)

          # Czyszczenie numeru zestawu
          clean_set_match = re.search(r"(\d{3,5})-\d", raw_set_str)
          if clean_set_match:
            set_num_only = clean_set_match.group(1)
          else:
            set_num_only = raw_set_str.split("-")[0]

          # 3. Niezawodne wyciąganie nazwy zestawu
          lines = [line.strip() for line in block.split("\n") if line.strip()]
          set_name = "Zestaw LEGO"

          for i, line in enumerate(lines):
            if line in ["New", "Sealed"] and i + 1 < len(lines):
              for k in range(i + 1, len(lines)):
                candidate = lines[k]
                if (
                    candidate
                    and candidate != "Sealed"
                    and candidate != "Complete"
                    and not candidate.startswith("- All Items")
                    and not candidate.startswith("Quantity")
                    and not candidate.startswith("Price")
                    and "~PLN" not in candidate
                ):
                  set_name = candidate
                  break
              break

          matches.append({
              "numer": set_num_only,
              "nazwa": set_name,
              "bl_pln": bl_pln_price,
          })

    if matches:
      results = []
      progress_bar = st.progress(0)
      total_matches = len(matches)

      for idx, item in enumerate(matches):
        set_clean = item["numer"]
        bl_price = item["bl_pln"]

        # Pobieranie ceny z Promoklocki
        pl_price = get_promoklocki_price(set_clean)

        # Obliczanie zysku bezwzględnego i procentowego (ROI)
        if pl_price > 0:
          zysk_abs = pl_price - bl_price
          zysk_rel = (zysk_abs / bl_price) * 100 if bl_price > 0 else 0
        else:
          zysk_abs = 0.0
          zysk_rel = 0.0

        results.append({
            "Numer": item["numer"],
            "Nazwa zestawu": item["nazwa"],
            "Cena BrickLink (PLN)": round(bl_price, 2),
            "Cena Promoklocki (PLN)": pl_price,
            "Zysk (PLN)": round(zysk_abs, 2),
            "Zysk (%)": round(zysk_rel, 1),
        })

        progress_bar.progress((idx + 1) / total_matches)

      progress_bar.empty()

      # Zapisujemy wyniki w pamięci sesji
      st.session_state["results_df"] = pd.DataFrame(results)
      st.session_state["success_msg"] = (
          f"Sukces! Przeanalizowano {len(results)} nowych zestawów (odrzucono"
          " używane i kolekcjonerskie)."
      )

      # Zlecamy czyszczenie pola i odświeżenie
      st.session_state["clear_pending"] = True
      st.rerun()
    else:
      st.error(
          "Nie znaleziono pasujących zestawów (lub wszystkie były pozycjami"
          " kolekcjonerskimi / używanymi)."
      )

# Wyświetlanie tabeli z pamięci sesji (jeśli istnieje)
if st.session_state["results_df"] is not None:
  st.success(st.session_state["success_msg"])
  st.dataframe(
      st.session_state["results_df"].sort_values(
          by="Zysk (PLN)", ascending=False
      ),
      use_container_width=True,
  )
