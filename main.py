import requests
from bs4 import BeautifulSoup
import random
from datetime import datetime, date
import locale
import sys
import time  # Artık kullanılmıyor ama import kalabilir
from flask import Flask, render_template, request, redirect, url_for

# --- Türkçe Locale Ayarı ---
try:
    locale.setlocale(locale.LC_TIME, 'tr_TR.UTF-8')
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'turkish')
    except locale.Error:
        print("Uyarı: Sistemde Türkçe locale ayarlanamadı.", file=sys.stderr)


# --- Veri Çekme Fonksiyonu (API + Limit + Görsel URL) ---
def fetch_istanbul_plays():
    """tiyatrolar.com.tr API'sini kullanarak İstanbul oyunlarını çeker (Limitli)."""
    api_url = "https://tiyatrolar.com.tr/frontend/load_more_activity_via_ajax/?il=34"
    plays = []
    error_message = None
    offset = 21  # İlk dinamik yükleme offset'i
    item_count_per_request = 0
    request_count = 0
    MAX_REQUESTS = 6  # Zaman aşımını önlemek için istek limiti

    headers = {
        'User-Agent':
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Referer': 'https://tiyatrolar.com.tr/sahnedekiler/?il=34'
    }

    print("Oyunlar API'den çekiliyor (Limitli)...")

    while True:
        if request_count >= MAX_REQUESTS:
            print(
                f"İstek limiti ({MAX_REQUESTS}) doldu. Oyun çekme durduruldu.")
            break

        payload = {'offset': offset, 'activity_type_id': '1'}
        request_count += 1
        print(
            f"İstek #{request_count} gönderiliyor: offset={offset}, activity_type_id=1"
        )

        try:
            response = requests.post(api_url,
                                     data=payload,
                                     headers=headers,
                                     timeout=20)
            response.raise_for_status()

            try:
                data = response.json()
            except requests.exceptions.JSONDecodeError:
                print(
                    f"Offset {offset} yanıtı JSON formatında değil. Yanıt: {response.text[:200]}",
                    file=sys.stderr)
                break

            if data.get('sta') == 1 and 'html' in data:
                html_fragment_str = data.get('html', '')
                if not html_fragment_str.strip():
                    print(
                        f"Offset {offset} yanıtı başarılı ama HTML içeriği boş. Daha fazla oyun yok."
                    )
                    break

                soup_fragment = BeautifulSoup(html_fragment_str, 'html.parser')
                new_items = soup_fragment.select('.theater-item')

                if not new_items:
                    print(
                        f"Offset {offset} HTML yanıtı içinde '.theater-item' bulunamadı veya daha fazla oyun yok."
                    )
                    break

                print(f"{len(new_items)} yeni oyun bulundu.")
                item_count_per_request = len(new_items)

                for item in new_items:
                    parsed_date = None
                    formatted_time = None
                    name = None
                    venue = None
                    image_url = None  # Görsel URL'si için değişken

                    try:
                        name_tag = item.select_one('h3 a')
                        if name_tag: name = name_tag.text.strip()

                        venue_tag = item.select_one('aside.post-meta a')
                        if venue_tag: venue = venue_tag.text.strip()

                        img_tag = item.select_one('figure img')
                        if img_tag:
                            if 'src' in img_tag.attrs:
                                image_url = img_tag[
                                    'src']  # Görsel URL'sini al
                            if 'alt' in img_tag.attrs:
                                alt_text = img_tag['alt'].strip()
                                parts = alt_text.split()
                                if len(parts) >= 2:
                                    date_str, time_str = parts[0], parts[1]
                                    try:
                                        parsed_date = datetime.strptime(
                                            date_str, "%Y-%m-%d").date()
                                        formatted_time = time_str[:5]
                                    except ValueError:
                                        parsed_date, formatted_time = None, None

                        if name and venue and parsed_date and formatted_time and image_url:
                            plays.append({
                                "name": name,
                                "venue": venue,
                                "date": parsed_date,
                                "time": formatted_time,
                                "image_url": image_url  # Görsel URL'sini ekle
                            })

                    except Exception as e:
                        print(f"Bir item işlenirken hata: {e}")
                        continue

                offset += item_count_per_request
                # time.sleep(0.5) # Kaldırıldı

            else:
                error_msg = data.get(
                    'msg', 'Bilinmeyen hata veya geçersiz JSON yapısı')
                print(
                    f"API başarısız yanıt döndürdü (offset={offset}): sta={data.get('sta')}, msg={error_msg}"
                )
                break

        except requests.exceptions.Timeout:
            error_message = f"API isteği zaman aşımına uğradı (offset={offset}). Daha önce bulunanlar listeleniyor."
            print(error_message, file=sys.stderr)
            break
        except requests.exceptions.RequestException as e:
            if e.response is not None:
                error_message = f"API isteği başarısız oldu (offset={offset}): {e.response.status_code} {e.response.reason}. Daha önce bulunanlar listeleniyor."
            else:
                error_message = f"API isteği başarısız oldu (offset={offset}): {e}. Daha önce bulunanlar listeleniyor."
            print(error_message, file=sys.stderr)
            break
        except Exception as e:
            error_message = f"Veri işlenirken beklenmedik hata (offset={offset}): {e}. Daha önce bulunanlar listeleniyor."
            print(error_message, file=sys.stderr)
            break

    print(f"Toplam {len(plays)} oyun çekildi (Limit: {MAX_REQUESTS} istek).")
    return plays, error_message


# --- Flask Uygulaması ---
app = Flask(__name__)
app.jinja_env.globals['locale'] = locale


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        try:
            selected_date_str = request.form.get('selected_date')
            if not selected_date_str:
                return render_template('index.html',
                                       error="Lütfen bir tarih seçin.")

            selected_date = datetime.strptime(selected_date_str,
                                              "%Y-%m-%d").date()

            all_plays, fetch_error = fetch_istanbul_plays()
            result_message = fetch_error if fetch_error else None

            if not all_plays and not fetch_error:
                return render_template(
                    'result.html',
                    message=
                    "API'den hiç oyun bilgisi alınamadı veya dönen veride oyun bulunamadı."
                )
            elif not all_plays and fetch_error:
                return render_template(
                    'index.html', error=f"Veri çekme hatası: {fetch_error}")

            filtered_plays = [
                play for play in all_plays
                if play.get('date') and play['date'] == selected_date
            ]

            if not filtered_plays:
                message = f"{selected_date.strftime('%d.%m.%Y')} tarihinde (API'den çekilen oyunlar içinde) gösterimde olan oyun bulunamadı."
                if result_message: message += f" (Not: {result_message})"
                return render_template('result.html', message=message)
            else:
                random_play = random.choice(filtered_plays)
                return render_template('result.html',
                                       play=random_play,
                                       message=result_message)

        except ValueError:
            return render_template('index.html',
                                   error="Lütfen geçerli bir tarih seçin.")
        except Exception as e:
            print(f"İstek işlenirken hata: {e}", file=sys.stderr)
            return render_template('index.html', error=f"Bir hata oluştu: {e}")

    # GET isteği ise sadece formu göster
    return render_template('index.html')


