import os
import glob
import math
import zipfile
import io
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import matplotlib.image as mpimg
import cairosvg
from PIL import Image

# ==========================================
# ⚙️ 使用者設定區
# ==========================================

# 下載設定 (請填寫您的 API 授權碼)
CWA_ZIP_URL = "https://cwaopendata.s3.ap-northeast-1.amazonaws.com/Forecast/F-D0047-093.zip"

# 檔案目錄設定
WORK_DIR = r"D:\ec\Autorun_seanthink\Weather_Cards"
BASE_IMG_PATH = r"D:\ec\Autorun_seanthink\custom_background.png"         # 您的通用底圖 (4570x2571)
ICON_DIR = r"D:\cwa weather icon\ncdr"                      # SVG 天氣圖示資料夾
OUTPUT_DIR = os.path.join(WORK_DIR, "Output_368")

# 字體路徑
FONT_GEN_NORMAL = r"D:\ec\Autorun_seanthink\GenJyuuGothic-Normal.ttf"
FONT_YUAN_HEAVY = r"D:\ec\Autorun_seanthink\GenSekiGothic2TW-H2.ttf"
# 新增這行：設定王漢宗特黑體路徑
FONT_HANWANG_HEAVY = r"D:\ec\Autorun_seanthink\HanWangHeiHeavy.ttf"
# 並且在字型物件初始化區域新增：
# ==========================================
# 🛠 座標常數區 (已套用修正後的座標)
# ==========================================
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(os.path.join(WORK_DIR, "xml_data"), exist_ok=True)

# 字型物件初始化
font_hanwang = FontProperties(fname=FONT_HANWANG_HEAVY)
font_yuan_h = FontProperties(fname=FONT_YUAN_HEAVY)
font_gen_n = FontProperties(fname=FONT_GEN_NORMAL)

# 大資訊 X 座標
BIG_X = [287, 826.5, 1374.7]
BIG_DATES_X = [278.8, 819.3, 1366.2]
BIG_DAYS_X = [315.1, 855.6, 1402.5]
BIG_POP_X = [304.9, 857.8, 1402.5]        # 修正後的降雨機率
BIG_WIND_SCALE_X = [367.2, 901.5, 1435.8] # 修正後的風級
BIG_ICON_X = [257.1, 791.4, 1325.6]

# 小資訊 X 座標 (Day 1 到 Day 7)
SMALL_DATES_X = [2005.2, 2383.9, 2751.8, 3116.7, 3488.6, 3856, 4226.3]
SMALL_DAYS_X = [2023.5, 2402.1, 2764.4, 3134.9, 3507.9, 3875.9, 4246.4]
SMALL_POP_X = [2045.3, 2414.9, 2784.5] # 只有前三天
SMALL_ICON_X = [2018.6, 2378.5, 2757, 3130.3, 3495.5, 3861.8, 4233.9]

# 圖表 X 座標
CHART_X = [2088, 2459.2, 2830, 3201.5, 3572.6, 3943.8, 4314.9]
AREA_X = [2090, 2461.1, 2833, 3207, 3578.9, 3954.6, 4327.4]

# ==========================================
# 📊 繪圖輔助模組
# ==========================================

def draw_svg_icon(ax, svg_path, box_x, box_y, box_w, box_h):
    """載入 SVG 並繪製在指定座標框內"""
    if not os.path.exists(svg_path):
        return
    try:
        # SVG 轉 PNG
        png_data = cairosvg.svg2png(url=svg_path, output_width=int(box_w), output_height=int(box_h))
        img = Image.open(io.BytesIO(png_data))
        # extent=[left, right, bottom, top] (因為 y 軸已經反轉，所以 bottom=y+h, top=y)
        ax.imshow(img, extent=[box_x, box_x + box_w, box_y + box_h, box_y], zorder=5)
    except Exception as e:
        print(f"圖示載入錯誤 {svg_path}: {e}")

def calculate_wind_angle(direction_str):
    """中文字串轉風向角度"""
    dir_map = {
        "北": 0, "東北": 45, "東": 90, "東南": 135,
        "南": 180, "西南": 225, "西": 270, "西北": 315
    }
    for key, angle in dir_map.items():
        if key in direction_str:
            return angle
    return 0

# ==========================================
# 繪製風向箭頭 (支援顏色調整)
# ==========================================
def draw_wind_arrow(ax, cx, cy, angle, line_width=9, color='#000000'):
    """繪製中心點在 (cx, cy) 的旋轉風向箭頭 (已改為黑色)"""
    length = 61.9
    rad = math.radians(angle - 90)
    
    dx = (length/2) * math.cos(rad)
    dy = (length/2) * math.sin(rad)
    start_x, start_y = cx - dx, cy - dy
    end_x, end_y = cx + dx, cy + dy
    
    ax.plot([start_x, end_x], [start_y, end_y], color=color, linewidth=line_width, zorder=8)
    
    hrad1 = math.radians(angle - 90 + 150)
    hrad2 = math.radians(angle - 90 - 150)
    hlen = 20
    hx1, hy1 = end_x + hlen * math.cos(hrad1), end_y + hlen * math.sin(hrad1)
    hx2, hy2 = end_x + hlen * math.cos(hrad2), end_y + hlen * math.sin(hrad2)
    
    ax.plot([end_x, hx1], [end_y, hy1], color=color, linewidth=line_width, zorder=8)
    ax.plot([end_x, hx2], [end_y, hy2], color=color, linewidth=line_width, zorder=8)

# ==========================================
# 📊 繪圖輔助模組 (支援字元間距)
# ==========================================
def draw_canva_text(ax, text, box_x, box_y, box_w, box_h, font_prop, fontsize, color='white', letter_spacing=None):
    """使用 Matplotlib 模擬 Canva 置中定位，並支援字元間距"""
    font_prop.set_size(fontsize)
    cx = box_x + box_w / 2
    cy = box_y + box_h / 2
    
    if letter_spacing is not None:
        # 將字串拆解，依據間距倍率逐字置中繪製
        chars = list(text)
        n = len(chars)
        # 估算總寬度 (字型大小 * 字數 + 間距空間)
        char_w = fontsize
        total_w = (n * char_w) + (n - 1) * (char_w * letter_spacing)
        start_x = cx - total_w / 2 + char_w / 2
        
        for i, c in enumerate(chars):
            # 每個字依序往右偏移
            ax.text(start_x + i * char_w * (1 + letter_spacing), cy, c, 
                    fontproperties=font_prop, color=color, ha='center', va='center', zorder=10)
    else:
        ax.text(cx, cy, text, fontproperties=font_prop, color=color, ha='center', va='center', zorder=10)

# ==========================================
# 🖼 核心繪圖邏輯 (Matplotlib 架構 - Canva 座標系)
# ==========================================
def generate_township_card(base_img, county, town, forecast_data, output_path):
    fig, ax = plt.subplots(figsize=(45.70, 25.71), dpi=100)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    
    ax.set_xlim(0, 4570)
    ax.set_ylim(2571, 0) 
    ax.axis('off')

    ax.imshow(base_img, extent=[0, 4570, 2571, 0], zorder=0)

    # --- 1. 繪製主標題 (加入字距 1.5) ---
    title_text = f"{county}{town} 天氣預報"
    # letter_spacing=1.5 模擬 Canva 上的字距推開效果
    draw_canva_text(ax, title_text, 1235.4, 50, 2099.1, 176.5, font_hanwang, 110, color='#094d88', letter_spacing=1.5)

    days = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    
    all_max_t = [int(day['MaxT']) for day in forecast_data[:7]]
    all_min_t = [int(day['MinT']) for day in forecast_data[:7]]
    
    chart_max_t, chart_min_t = max(all_max_t), min(all_min_t) 
    
    # 新增專屬大溫度的 X 座標常數 (依據您的新需求)
    BIG_MAX_X = [295.1, 834.1, 1377.1]
    BIG_MIN_X = [283.6, 826.5, 1374.7]
    
    area_y_vals = []

    for i in range(7):
        data = forecast_data[i]
        date_obj = data['date']
        day_str = days[date_obj.weekday()]
        date_str = date_obj.strftime("%m/%d")

        # --- 大資訊區 (1-3天) ---
        if i < 3:
            draw_canva_text(ax, day_str, BIG_DAYS_X[i], 726.4, 156.4, 70, font_gen_n, 50, color='#000000')
            draw_canva_text(ax, date_str, BIG_DATES_X[i], 835.2, 228.9, 72.3, font_gen_n, 50, color='#000000')
            
            # 最高溫度大 (新座標與尺寸)
            draw_canva_text(ax, f"{data['MaxT']}°", BIG_MAX_X[i], 1321.5, 199.2, 100.9, font_yuan_h, 85, color='#d2171f')
            # 最低溫度大 (新座標與尺寸)
            draw_canva_text(ax, f"{data['MinT']}°", BIG_MIN_X[i], 1489.0, 211.9, 140.6, font_yuan_h, 85, color='#094d88')
            
            draw_canva_text(ax, f"{data['PoP']}%", BIG_POP_X[i], 1836.4, 169.3, 57.1, font_gen_n, 50, color='#000000')
            
            # 繪製風向箭頭
            cx = BIG_X[i] + (211.9 / 2) # 維持原中心對齊
            draw_wind_arrow(ax, cx, 2151.45, calculate_wind_angle(data['WindDir']), color='#000000')

            icon_path = os.path.join(ICON_DIR, f"weather-{data['WxCode']}-c2.svg")
            draw_svg_icon(ax, icon_path, BIG_ICON_X[i], 947.3, 302.2, 302.2)

        # --- 小資訊區 (1-7天) ---
        draw_canva_text(ax, day_str, SMALL_DAYS_X[i], 655.5, 133.1, 66.8, font_gen_n, 40, color='#000000')
        draw_canva_text(ax, date_str, SMALL_DATES_X[i], 729.9, 169.6, 66.8, font_gen_n, 40, color='#000000')
        
        if i < 3:
            draw_canva_text(ax, f"{data['PoP']}%", SMALL_POP_X[i], 1652.9, 146.5, 70.2, font_gen_n, 45, color='#000000')
            
        icon_path_s = os.path.join(ICON_DIR, f"weather-{data['WxCode']}-c2.svg")
        draw_svg_icon(ax, icon_path_s, SMALL_ICON_X[i], 472.1, 158, 158)

        # --- 計算面積圖點位 ---
        ws_str = str(data['WindSpeed']).replace('>', '').replace('<', '').replace('=', '').strip()
        try:
            ws_val = float(ws_str)
        except ValueError:
            ws_val = 0.0 # 預設防呆
            
        ws_level = max(1, min(5, round((ws_val / 19.2) * 5)))
        y_area = 1398.5 - (1398.5 - 1264.2) * ((ws_level - 1) / 4)
        area_y_vals.append(y_area)

    # --- 2. 繪製圖表 ---
    ax.fill_between(AREA_X, [1398.5]*7, area_y_vals, color='#7ed957', zorder=2)
    
    y_range = 1153.6 - 910.1
    temp_range = max(1, chart_max_t - chart_min_t)
    
    y_max_points = []
    y_min_points = []
    
    # 先收集所有 Y 座標以便連線
    for i in range(7):
        y_max = 910.1 + y_range * (1 - (all_max_t[i] - chart_min_t) / temp_range)
        y_min = 910.1 + y_range * (1 - (all_min_t[i] - chart_min_t) / temp_range)
        y_max_points.append(y_max)
        y_min_points.append(y_min)

    # 繪製折線圖與圓點連線 (一次畫出整條線)
    ax.plot(CHART_X, y_max_points, color='#ff3131', linewidth=7, marker='o', markersize=18, zorder=6)
    ax.plot(CHART_X, y_min_points, color='#004aad', linewidth=6, marker='o', markersize=18, zorder=6)

    # 繪製圖表上的溫度文字 (新尺寸 Width: 53.5, Height: 43)
    for i in range(7):
        # 由於 Width=53.5，計算 X 起點 = CHART_X[i] - 53.5/2
        text_box_x = CHART_X[i] - 26.75 
        
        # 最高溫文字：位置在點上方 36.3 像素
        # (因為 Canva Y軸向下，放在上方代表 Y 要減去 36.3 和 Height 43)
        draw_canva_text(ax, f"{all_max_t[i]}", text_box_x, y_max_points[i] - 36.3 - 43, 53.5, 43, font_yuan_h, 35, color='#ff3131')
        
        # 最低溫文字：位置在點下方 36.3 像素
        draw_canva_text(ax, f"{all_min_t[i]}", text_box_x, y_min_points[i] + 36.3, 53.5, 43, font_yuan_h, 35, color='#004aad')

    # --- 3. 存檔與釋放 ---
    fig.savefig(output_path, dpi=100)
    plt.close(fig)

# ==========================================
# 📥 資料處理與啟動邏輯 (修正 XML 標籤問題)
# ==========================================
def process_all_xmls(xml_dir):
    xml_files = glob.glob(os.path.join(xml_dir, "*_Week24_CH.xml"))
    if not xml_files:
        print("找不到 XML 檔案。")
        return

    base_img = mpimg.imread(BASE_IMG_PATH)
    count = 0

    for xml_file in xml_files:
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            
            # 【關鍵】強制移除所有 XML Namespace，無視標籤前綴
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}', 1)[1]
                    
            # 配合範例檔案，使用首字母大寫的標籤名稱
            locations_node = root.find('.//Locations')
            if locations_node is None: 
                continue
            
            locations_name = locations_node.find('LocationsName').text
            
            for location in locations_node.findall('Location'):
                town_name = location.find('LocationName').text
                geocode = location.find('Geocode').text.strip()
                daily_data = {}
                
                # 遍歷所有的 Time 節點 (直接搜尋不分類別，更穩固)
                for time_node in location.findall('.//Time'):
                    st_node = time_node.find('StartTime')
                    if st_node is None: st_node = time_node.find('DataTime')
                    if st_node is None: continue
                    
                    dt_str = st_node.text[:10] # 擷取 YYYY-MM-DD
                    
                    if dt_str not in daily_data:
                        daily_data[dt_str] = {
                            'date': datetime.strptime(dt_str, "%Y-%m-%d"),
                            'MaxT': '0', 'MinT': '0', 'PoP': '0', 
                            'WxCode': '01', 'WindSpeed': '0', 
                            'WindDir': '偏北風', 'WindScale': '3級風'
                        }
                    
                    ev = time_node.find('ElementValue')
                    if ev is None: continue

                    # 依據您提供的欄位名稱直接對應抓取
                    mapping = [
                        ('MaxTemperature', 'MaxT'),
                        ('MinTemperature', 'MinT'),
                        ('ProbabilityOfPrecipitation', 'PoP'),
                        ('WeatherCode', 'WxCode'),
                        ('WindSpeed', 'WindSpeed'),
                        ('WindDirection', 'WindDir'),
                        ('BeaufortScale', 'WindScale')
                    ]
                    
                    for xml_tag, dict_key in mapping:
                        node = ev.find(xml_tag)
                        if node is not None and node.text:
                            val = node.text.strip()
                            if val and val != ' ':
                                # 保留第一筆讀到的資料 (通常是白天)
                                if daily_data[dt_str][dict_key] in ('0', '01', '偏北風', '3級風'):
                                    if dict_key == 'WxCode':
                                        daily_data[dt_str][dict_key] = val.zfill(2)
                                    else:
                                        daily_data[dt_str][dict_key] = val

                sorted_dates = sorted(daily_data.keys())
                forecast_data = [daily_data[d] for d in sorted_dates]
                
                # 若七天資料都有了就開始畫圖
                if len(forecast_data) >= 7:
                    out_path = os.path.join(OUTPUT_DIR, f"{geocode}.png")
                    generate_township_card(base_img, locations_name, town_name, forecast_data[:7], out_path)
                    count += 1
                    print(f"進度: 已輸出 {count}/368 張 ({locations_name}{town_name})     ", end='\r')
                    
        except Exception as e:
            print(f"\n解析檔案 {xml_file} 失敗: {e}")
            
    print(f"\n✓ 總共成功輸出 {count} 張鄉鎮預報圖卡！")

def main():
    print("=== CWA Matplotlib 預報圖卡自動化 ===")
    xml_dir = os.path.join(WORK_DIR, "xml_data")
    
    # 若沒有暫存檔案則下載
    print("1. 下載 ZIP...")
    r = requests.get(CWA_ZIP_URL)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        z.extractall(xml_dir)
            
    print("\n2. 開始產圖 (共368鄉鎮，請耐心等候)...")
    process_all_xmls(xml_dir)
    print("\n=== 全部完成！ ===")

if __name__ == "__main__":
    main()