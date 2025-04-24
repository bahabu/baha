import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime, date
import locale
import sys
import time
from flask import Flask, render_template, request, redirect, url_for

# --- Türkçe Locale Ayarı ---
try:
    locale.setlocale(locale.LC_TIME, 'tr_TR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'turkish')
    except locale.Error:
        print("Uyarı: Sistemde Türkçe locale ayarlanamadı.", file=sys.stderr)

# --- Veri Çekme Fonksiyonu (Değişiklik Yok) ---
def fetch_istanbul_plays():
    """tiyatrolar.com.tr API'sini kullanarak İstanbul oyunlarını çeker (Limitli)."""
    api_url = "https://tiyatrolar.com.tr/frontend/load_more_activity_via_ajax/?il=34"
    plays = []
    error_message = None
    offset = 21
    item_count_per_request = 0
    request_count = 0
    MAX_REQUESTS = 6

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Referer': 'https://tiyatrolar.com.tr/sahnedekiler/?il=34'
    }
    print("Oyunlar API'den çekiliyor (Limitli)...")
    while True:
        if request_count >= MAX_REQUESTS:
            print(f"İstek limiti ({MAX_REQUESTS}) doldu. Oyun çekme durduruldu.")
            break
        payload = {'offset': offset, 'activity_type_id': '1'}
        request_count += 1
        print(f"İstek #{request_count} gönderiliyor: offset={offset}, activity_type_id=1")
        try:
            response = requests.post(api_url, data=payload, headers=headers, timeout=20)
            response.raise_for_status()
            try:
                data = response.json()
            except requests.exceptions.JSONDecodeError:
                print(f"Offset {offset} yanıtı JSON formatında değil.", file=sys.stderr)
                break
            if data.get('sta') == 1 and 'html' in data:
                html_fragment_str = data.get('html', '')
                if not html_fragment_str.strip():
                    print(f"Offset {offset} yanıtı başarılı ama HTML içeriği boş.")
                    break
                soup_fragment = BeautifulSoup(html_fragment_str, 'html.parser')
                new_items = soup_fragment.select('.theater-item')
                if not new_items:
                    print(f"Offset {offset} HTML yanıtı içinde '.theater-item' bulunamadı.")
                    break
                print(f"{len(new_items)} yeni oyun bulundu.")
                item_count_per_request = len(new_items)
                for item in new_items:
                    parsed_date, formatted_time, name, venue, image_url = None, None, None, None, None
                    try:
                        name_tag = item.select_one('h3 a')
                        if name_tag: name = name_tag.text.strip()
                        venue_tag = item.select_one('aside.post-meta a')
                        if venue_tag: venue = venue_tag.text.strip()
                        img_tag = item.select_one('figure img')
                        if img_tag:
                            if 'src' in img_tag.attrs: image_url = img_tag['src']
                            if 'alt' in img_tag.attrs:
                                alt_text = img_tag['alt'].strip()
                                parts = alt_text.split()
                                if len(parts) >= 2:
                                    date_str, time_str = parts[0], parts[1]
                                    try:
                                        parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                                        formatted_time = time_str[:5]
                                    except ValueError: parsed_date, formatted_time = None, None
                        if name and venue and parsed_date and formatted_time and image_url:
                            plays.append({"name": name, "venue": venue, "date": parsed_date, "time": formatted_time, "image_url": image_url})
                    except Exception as e: print(f"Bir item işlenirken hata: {e}")
                offset += item_count_per_request
            else:
                error_msg = data.get('msg', 'Bilinmeyen hata veya geçersiz JSON yapısı')
                print(f"API başarısız yanıt (offset={offset}): sta={data.get('sta')}, msg={error_msg}")
                break
        except requests.exceptions.Timeout: error_message = f"API isteği zaman aşımı (offset={offset})"; print(error_message, file=sys.stderr); break
        except requests.exceptions.RequestException as e:
            error_message = f"API isteği başarısız (offset={offset}): {e}"; print(error_message, file=sys.stderr); break
        except Exception as e: error_message = f"Veri işlenirken hata (offset={offset}): {e}"; print(error_message, file=sys.stderr); break
    print(f"Toplam {len(plays)} oyun çekildi (Limit: {MAX_REQUESTS} istek).")
    return plays, error_message

# --- Flask Uygulaması (7 Mayıs kontrolü güncellendi) ---
app = Flask(__name__)
app.jinja_env.globals['locale'] = locale

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            selected_date_str = request.form.get('selected_date')
            if not selected_date_str:
                 return render_template('index.html', error="Lütfen bir tarih seçin.")

            selected_date = datetime.strptime(selected_date_str, "%Y-%m-%d").date()

            # === 7 Mayıs Kontrolü (Sadece işaretçi ayarla) ===
            current_year = datetime.now().year
            may_7 = date(current_year, 5, 7)
            is_may_7 = (selected_date == may_7) # True ya da False olacak
            # ============================================

            # Normal işlemlere devam et
            all_plays, fetch_error = fetch_istanbul_plays()
            result_message = fetch_error if fetch_error else None

            if not all_plays and not fetch_error:
                 # 7 Mayıs ise özel mesaj yerine bu mesajı gönderme, şablonda halledilecek
                 if not is_may_7:
                    return render_template('result.html', message="API'den hiç oyun bilgisi alınamadı veya dönen veride oyun bulunamadı.", is_special_day=is_may_7)
                 else: # 7 Mayıs ama API'den hiç oyun gelmediyse (limitli fetch nedeniyle olabilir)
                     # Yine de özel günü kutla, oyun olmasa bile
                      return render_template('result.html', message="API'den oyun çekilemedi ama...", is_special_day=is_may_7)

            elif not all_plays and fetch_error:
                 return render_template('index.html', error=f"Veri çekme hatası: {fetch_error}")

            # Seçilen tarihe göre filtrele (7 Mayıs olsa bile)
            filtered_plays = [
                play for play in all_plays
                if play.get('date') and play['date'] == selected_date
            ]

            if not filtered_plays:
                # 7 Mayıs ise özel mesaj şablonda gösterilecek, oyun bulunamadı mesajı gereksiz
                if not is_may_7:
                    message = f"{selected_date.strftime('%d.%m.%Y')} tarihinde (API'den çekilen oyunlar içinde) gösterimde olan oyun bulunamadı."
                    if result_message: message += f" (Not: {result_message})"
                    # Oyun bulunamasa bile is_may_7 bilgisini gönder
                    return render_template('result.html', message=message, is_special_day=is_may_7)
                else:
                    # 7 Mayıs'ta oyun bulunamadıysa sadece özel gün flag'ini gönder, mesaj şablonda
                     return render_template('result.html', is_special_day=is_may_7)
            else:
                # Oyun bulunduysa rastgele seç
                random_play = random.choice(filtered_plays)
                # Hem oyunu hem de özel gün bilgisini gönder
                return render_template('result.html', play=random_play, message=result_message, is_special_day=is_may_7)

        except ValueError:
             return render_template('index.html', error="Lütfen geçerli bir tarih seçin.")
        except Exception as e:
             print(f"İstek işlenirken hata: {e}", file=sys.stderr)
             return render_template('index.html', error=f"Bir hata oluştu: {e}")

    # GET isteği ise sadece formu göster
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')