import gzip
import math
import os
import re
import traceback
from urllib.request import urlretrieve

from flask import Flask, request, jsonify
from flask_cors import CORS
import mwapi
from mwparserfromhtml import Article
from mwparserfromhtml.parse.utils import is_transcluded
import requests
import yaml


app = Flask(__name__)
__dir__ = os.path.dirname(__file__)

WIKIPEDIA_LANGUAGE_CODES = ['aa', 'ab', 'ace', 'ady', 'af', 'ak', 'als', 'am', 'an', 'ang', 'ar', 'arc', 'ary', 'arz', 'as', 'ast', 'atj', 'av', 'avk', 'awa', 'ay', 'az', 'azb', 'ba', 'ban', 'bar', 'bat-smg', 'bcl', 'be', 'be-x-old', 'bg', 'bh', 'bi', 'bjn', 'bm', 'bn', 'bo', 'bpy', 'br', 'bs', 'bug', 'bxr', 'ca', 'cbk-zam', 'cdo', 'ce', 'ceb', 'ch', 'cho', 'chr', 'chy', 'ckb', 'co', 'cr', 'crh', 'cs', 'csb', 'cu', 'cv', 'cy', 'da', 'de', 'din', 'diq', 'dsb', 'dty', 'dv', 'dz', 'ee', 'el', 'eml', 'en', 'eo', 'es', 'et', 'eu', 'ext', 'fa', 'ff', 'fi', 'fiu-vro', 'fj', 'fo', 'fr', 'frp', 'frr', 'fur', 'fy', 'ga', 'gag', 'gan', 'gcr', 'gd', 'gl', 'glk', 'gn', 'gom', 'gor', 'got', 'gu', 'gv', 'ha', 'hak', 'haw', 'he', 'hi', 'hif', 'ho', 'hr', 'hsb', 'ht', 'hu', 'hy', 'hyw', 'hz', 'ia', 'id', 'ie', 'ig', 'ii', 'ik', 'ilo', 'inh', 'io', 'is', 'it', 'iu', 'ja', 'jam', 'jbo', 'jv', 'ka', 'kaa', 'kab', 'kbd', 'kbp', 'kg', 'ki', 'kj', 'kk', 'kl', 'km', 'kn', 'ko', 'koi', 'kr', 'krc', 'ks', 'ksh', 'ku', 'kv', 'kw', 'ky', 'la', 'lad', 'lb', 'lbe', 'lez', 'lfn', 'lg', 'li', 'lij', 'lld', 'lmo', 'ln', 'lo', 'lrc', 'lt', 'ltg', 'lv', 'mai', 'map-bms', 'mdf', 'mg', 'mh', 'mhr', 'mi', 'min', 'mk', 'ml', 'mn', 'mnw', 'mr', 'mrj', 'ms', 'mt', 'mus', 'mwl', 'my', 'myv', 'mzn', 'na', 'nah', 'nap', 'nds', 'nds-nl', 'ne', 'new', 'ng', 'nl', 'nn', 'no', 'nov', 'nqo', 'nrm', 'nso', 'nv', 'ny', 'oc', 'olo', 'om', 'or', 'os', 'pa', 'pag', 'pam', 'pap', 'pcd', 'pdc', 'pfl', 'pi', 'pih', 'pl', 'pms', 'pnb', 'pnt', 'ps', 'pt', 'qu', 'rm', 'rmy', 'rn', 'ro', 'roa-rup', 'roa-tara', 'ru', 'rue', 'rw', 'sa', 'sah', 'sat', 'sc', 'scn', 'sco', 'sd', 'se', 'sg', 'sh', 'shn', 'si', 'simple', 'sk', 'sl', 'sm', 'smn', 'sn', 'so', 'sq', 'sr', 'srn', 'ss', 'st', 'stq', 'su', 'sv', 'sw', 'szl', 'szy', 'ta', 'tcy', 'te', 'tet', 'tg', 'th', 'ti', 'tk', 'tl', 'tn', 'to', 'tpi', 'tr', 'ts', 'tt', 'tum', 'tw', 'ty', 'tyv', 'udm', 'ug', 'uk', 'ur', 'uz', 've', 'vec', 'vep', 'vi', 'vls', 'vo', 'wa', 'war', 'wo', 'wuu', 'xal', 'xh', 'xmf', 'yi', 'yo', 'za', 'zea', 'zh', 'zh-classical', 'zh-min-nan', 'zh-yue', 'zu']
MAX_QUAL_VALS = {}
MQV_FN = os.path.join(__dir__, 'quality-maxvals-by-wiki.tsv.gz')
SFN_TEMPLATES = [t.lower() for t in ["Shortened footnote template", "sfn", "Sfnp", "Sfnm", "Sfnmp"]]

COEF_LEN = 0.395
COEF_MED = 0.114
COEF_HEA = 0.123
COEF_REF = 0.181
COEF_LIN = 0.115
COEF_CAT = 0.070

# See: https://github.com/geohci/miscellaneous-wikimedia/blob/master/article-features/quality_model_features_V2.ipynb
MIN_MAX_MED = 2
MIN_MAX_CAT = 5
MIN_MAX_LEN = 100
MIN_MAX_HEA = 0.1
MIN_MAX_REF = 0.15
MIN_MAX_LIN = 0.1

MEDIA_PREFIXES = ['File', 'Image', 'Media']
CAT_PREFIXES = ['Category']

# https://commons.wikimedia.org/wiki/Commons:File_types
IMAGE_EXTENSIONS = ['.jpg', '.png', '.svg', '.gif', '.jpeg', '.tif', '.bmp', '.webp', '.xcf']
VIDEO_EXTENSIONS = ['.ogv', '.webm', '.mpg', '.mpeg']
AUDIO_EXTENSIONS = ['.ogg', '.mp3', '.mid', '.webm', '.flac', '.wav', '.oga']
MEDIA_EXTENSIONS = list(set(IMAGE_EXTENSIONS + VIDEO_EXTENSIONS + AUDIO_EXTENSIONS))
# build regex that checks for all media extensions
EXTEN_REGEX = ('(' + '|'.join([e + r'\b' for e in MEDIA_EXTENSIONS]) + ')').replace('.', r'\.')
# join in the extension regex with one that requiries at least one alphanumeric and/or a few special characters before it
EXTEN_PATTERN = re.compile(fr"([\w ',().-]+){EXTEN_REGEX}", flags=re.UNICODE)

MEDIA_ALIASES = {
    "ab": ["Медиа", "Файл", "Афаил", "Амедиа", "Изображение"],
    "ace": ["Beureukaih", "Gambar", "Alat", "Berkas"],
    "ady": ["Медиа"],
    "af": ["Lêer", "Beeld"],
    "als": ["Medium", "Datei", "Bild"],
    "am": ["ፋይል", "ስዕል"],
    "an": ["Imachen", "Imagen"],
    "ang": ["Ymele", "Biliþ"],
    "ar": ["ميديا", "صورة", "وسائط", "ملف"],
    "arc": ["ܠܦܦܐ", "ܡܝܕܝܐ"],
    "arz": ["ميديا", "صورة", "وسائط", "ملف"],
    "as": ["চিত্ৰ", "चित्र", "চিত্র", "মাধ্যম"],
    "ast": ["Imaxen", "Ficheru", "Imaxe", "Archivu", "Imagen", "Medios"],
    "atj": ["Tipatcimoctakewin", "Natisinahikaniwoc"],
    "av": ["Медиа", "Файл", "Изображение"],
    "ay": ["Medio", "Archivo", "Imagen"],
    "az": ["Mediya", "Şəkil", "Fayl"],
    "azb": ["رسانه", "تصویر", "مدیا", "فایل", "رسانه‌ای"],
    "ba": ["Медиа", "Рәсем", "Файл", "Изображение"],
    "bar": ["Medium", "Datei", "Bild"],
    "bat-smg": ["Vaizdas", "Medėjė", "Abruozdielis"],
    "bcl": ["Medio", "Ladawan"],
    "be": ["Мультымедыя", "Файл", "Выява"],
    "be-x-old": ["Мэдыя", "Файл", "Выява"],
    "bg": ["Медия", "Файл", "Картинка"],
    "bh": ["मीडिया", "चित्र"],
    "bjn": ["Barakas", "Gambar", "Berkas"],
    "bm": ["Média", "Fichier"],
    "bn": ["চিত্র", "মিডিয়া"],
    "bpy": ["ছবি", "মিডিয়া"],
    "br": ["Skeudenn", "Restr"],
    "bs": ["Mediji", "Slika", "Datoteka", "Medija"],
    "bug": ["Gambar", "Berkas"],
    "bxr": ["Файл", "Меди", "Изображение"],
    "ca": ["Fitxer", "Imatge"],
    "cbk-zam": ["Medio", "Archivo", "Imagen"],
    "cdo": ["文件", "媒體", "圖像", "檔案"],
    "ce": ["Хlум", "Медиа", "Сурт", "Файл", "Медйа", "Изображение"],
    "ceb": ["Payl", "Medya", "Imahen"],
    "ch": ["Litratu"],
    "ckb": ["میدیا", "پەڕگە"],
    "co": ["Immagine"],
    "crh": ["Медиа", "Resim", "Файл", "Fayl", "Ресим"],
    "cs": ["Soubor", "Média", "Obrázok"],
    "csb": ["Òbrôzk", "Grafika"],
    "cu": ["Видъ", "Ви́дъ", "Дѣло", "Срѣдьства"],
    "cv": ["Медиа", "Ӳкерчĕк", "Изображение"],
    "cy": ["Delwedd"],
    "da": ["Billede", "Fil"],
    "de": ["Medium", "Datei", "Bild"],
    "din": ["Ciɛl", "Apamduööt"],
    "diq": ["Medya", "Dosya"],
    "dsb": ["Wobraz", "Dataja", "Bild", "Medija"],
    "dty": ["चित्र", "मिडिया"],
    "dv": ["ފައިލު", "މީޑިއާ", "ފައިލް"],
    "el": ["Εικόνα", "Αρχείο", "Μέσο", "Μέσον"],
    "eml": ["Immagine"],
    "eo": ["Dosiero", "Aŭdvidaĵo"],
    "es": ["Medio", "Archivo", "Imagen"],
    "et": ["Pilt", "Fail", "Meedia"],
    "eu": ["Irudi", "Fitxategi"],
    "ext": ["Archivu", "Imagen", "Mediu"],
    "fa": ["رسانه", "تصویر", "مدیا", "پرونده", "رسانه‌ای"],
    "ff": ["Média", "Fichier"],
    "fi": ["Kuva", "Tiedosto"],
    "fiu-vro": ["Pilt", "Meediä"],
    "fo": ["Miðil", "Mynd"],
    "fr": ["Média", "Fichier"],
    "frp": ["Émâge", "Fichiér", "Mèdia"],
    "frr": ["Medium", "Datei", "Bild"],
    "fur": ["Immagine", "Figure"],
    "fy": ["Ofbyld"],
    "ga": ["Íomhá", "Meán"],
    "gag": ["Mediya", "Medya", "Resim", "Dosya", "Dosye"],
    "gan": ["媒体文件", "文件", "文檔", "档案", "媒體", "图像", "圖像", "媒体", "檔案"],
    "gd": ["Faidhle", "Meadhan"],
    "gl": ["Imaxe", "Ficheiro", "Arquivo", "Imagem"],
    "glk": ["رسانه", "تصویر", "پرونده", "فاىل", "رسانه‌ای", "مديا"],
    "gn": ["Medio", "Imagen", "Ta'ãnga"],
    "gom": ["माध्यम", "मिडिया", "फायल"],
    "gor": ["Gambar", "Berkas"],
    "got": ["𐍆𐌴𐌹𐌻𐌰"],
    "gu": ["દ્રશ્ય-શ્રાવ્ય (મિડિયા)", "દ્રશ્ય-શ્રાવ્ય_(મિડિયા)", "ચિત્ર"],
    "gv": ["Coadan", "Meanyn"],
    "hak": ["文件", "媒體", "圖像", "檔案"],
    "haw": ["Kiʻi", "Waihona", "Pāpaho"],
    "he": ["תמונה", "קו", "מדיה", "קובץ"],
    "hi": ["मीडिया", "चित्र"],
    "hif": ["file", "saadhan"],
    "hr": ["Mediji", "DT", "Slika", "F", "Datoteka"],
    "hsb": ["Wobraz", "Dataja", "Bild"],
    "ht": ["Imaj", "Fichye", "Medya"],
    "hu": ["Kép", "Fájl", "Média"],
    "hy": ["Պատկեր", "Մեդիա"],
    "ia": ["Imagine", "Multimedia"],
    "id": ["Gambar", "Berkas"],
    "ig": ["Nká", "Midia", "Usòrò", "Ákwúkwó orünotu", "Ákwúkwó_orünotu"],
    "ii": ["媒体文件", "文件", "档案", "图像", "媒体"],
    "ilo": ["Midia", "Papeles"],
    "inh": ["Медиа", "Файл", "Изображение"],
    "io": ["Imajo", "Arkivo"],
    "is": ["Miðill", "Mynd"],
    "it": ["Immagine"],
    "ja": ["メディア", "ファイル", "画像"],
    "jbo": ["velsku", "datnyvei"],
    "jv": ["Barkas", "Medhia", "Gambar", "Médhia"],
    "ka": ["მედია", "სურათი", "ფაილი"],
    "kaa": ["Swret", "Таспа", "سۋرەت", "Taspa", "Su'wret", "Сурет", "تاسپا"],
    "kab": ["Tugna"],
    "kbd": ["Медиа", "Файл"],
    "kbp": ["Média", "Fichier"],
    "kg": ["Fisye"],
    "kk": ["Swret", "سۋرەت", "Таспа", "Taspa", "Сурет", "تاسپا"],
    "kl": ["Billede", "Fiileq", "Fil"],
    "km": ["ឯកសារ", "រូបភាព", "មេឌា", "មីឌា"],
    "kn": ["ಚಿತ್ರ", "ಮೀಡಿಯ"],
    "ko": ["미디어", "파일", "그림"],
    "koi": ["Медиа", "Файл", "Изображение"],
    "krc": ["Медиа", "Файл", "Изображение"],
    "ks": ["میڈیا", "فَیِل"],
    "ksh": ["Beld", "Meedije", "Medie", "Belld", "Medium", "Datei", "Meedijum", "Bild"],
    "ku": ["میدیا", "پەڕگە", "Medya", "Wêne"],
    "kv": ["Медиа", "Файл", "Изображение"],
    "kw": ["Restren"],
    "ky": ["Медиа", "Файл"],
    "la": ["Imago", "Fasciculus"],
    "lad": ["Dossia", "Medya", "Archivo", "Dosya", "Imagen", "Meddia"],
    "lb": ["Fichier", "Bild"],
    "lbe": ["Медиа", "Сурат", "Изображение"],
    "lez": ["Медиа", "Mediya", "Файл", "Şəkil", "Изображение"],
    "lfn": ["Fix"],
    "li": ["Afbeelding", "Plaetje", "Aafbeilding"],
    "lij": ["Immaggine", "Immagine"],
    "lmo": ["Immagine", "Imàjine", "Archivi"],
    "ln": ["Média", "Fichier"],
    "lo": ["ສື່ອ", "ສື່", "ຮູບ"],
    "lrc": ["رسانه", "تصویر", "رسانه‌ای", "جانیا", "أسگ", "ڤارئسگأر"],
    "lt": ["Vaizdas", "Medija"],
    "ltg": ["Medeja", "Fails"],
    "lv": ["Attēls"],
    "mai": ["मेडिया", "फाइल"],
    "map-bms": ["Barkas", "Medhia", "Gambar", "Médhia"],
    "mdf": ["Медиа", "Няйф", "Изображение"],
    "mg": ["Rakitra", "Sary", "Média"],
    "mhr": ["Медиа", "Файл", "Изображение"],
    "min": ["Gambar", "Berkas"],
    "mk": ["Податотека", "Медија", "Медиум", "Слика"],
    "ml": ["പ്രമാണം", "ചി", "മീഡിയ", "പ്ര", "ചിത്രം"],
    "mn": ["Медиа", "Файл", "Зураг"],
    "mr": ["चित्र", "मिडिया"],
    "mrj": ["Медиа", "Файл", "Изображение"],
    "ms": ["Fail", "Imej"],
    "mt": ["Midja", "Medja", "Stampa"],
    "mwl": ["Multimédia", "Fexeiro", "Ficheiro", "Arquivo", "Imagem"],
    "my": ["ဖိုင်", "မီဒီယာ"],
    "myv": ["Медия", "Артовкс", "Изображение"],
    "mzn": ["رسانه", "تصویر", "مه‌دیا", "مدیا", "پرونده", "رسانه‌ای"],
    "nah": ["Mēdiatl", "Īxiptli", "Imagen"],
    "nap": ["Fiùra", "Immagine"],
    "nds": ["Datei", "Bild"],
    "nds-nl": ["Ofbeelding", "Afbeelding", "Bestaand"],
    "ne": ["मीडिया", "चित्र"],
    "new": ["किपा", "माध्यम"],
    "nl": ["Bestand", "Afbeelding"],
    "nn": ["Fil", "Bilde", "Filpeikar"],
    "no": ["Fil", "Medium", "Bilde"],
    "nov": [],
    "nrm": ["Média", "Fichier"],
    "nso": ["Seswantšho"],
    "nv": ["Eʼelyaaígíí"],
    "oc": ["Imatge", "Fichièr", "Mèdia"],
    "olo": ["Kuva", "Medii", "Failu"],
    "or": ["ମାଧ୍ୟମ", "ଫାଇଲ"],
    "os": ["Ныв", "Медиа", "Файл", "Изображение"],
    "pa": ["ਤਸਵੀਰ", "ਮੀਡੀਆ"],
    "pcd": ["Média", "Fichier"],
    "pdc": ["Medium", "Datei", "Bild", "Feil"],
    "pfl": ["Dadai", "Medium", "Datei", "Bild"],
    "pi": ["मीडिया", "पटिमा"],
    "pl": ["Plik", "Grafika"],
    "pms": ["Figura", "Immagine"],
    "pnb": ["میڈیا", "تصویر", "فائل"],
    "pnt": ["Εικόνα", "Αρχείον", "Εικόναν", "Μέσον"],
    "ps": ["انځور", "رسنۍ", "دوتنه"],
    "pt": ["Multimédia", "Ficheiro", "Arquivo", "Imagem"],
    "qu": ["Midya", "Imagen", "Rikcha"],
    "rm": ["Multimedia", "Datoteca"],
    "rmy": ["Fişier", "Mediya", "Chitro", "Imagine"],
    "ro": ["Fişier", "Imagine", "Fișier"],
    "roa-rup": ["Fişier", "Imagine", "Fișier"],
    "roa-tara": ["Immagine"],
    "ru": ["Медиа", "Файл", "Изображение"],
    "rue": ["Медіа", "Медиа", "Файл", "Изображение", "Зображення"],
    "rw": ["Dosiye", "Itangazamakuru"],
    "sa": ["चित्रम्", "माध्यमम्", "सञ्चिका", "माध्यम", "चित्रं"],
    "sah": ["Миэдьийэ", "Ойуу", "Билэ", "Изображение"],
    "sat": ["ᱨᱮᱫ", "ᱢᱤᱰᱤᱭᱟ"],
    "sc": ["Immàgini"],
    "scn": ["Immagine", "Mmàggini", "Mèdia"],
    "sd": ["عڪس", "ذريعات", "فائل"],
    "se": ["Fiila"],
    "sg": ["Média", "Fichier"],
    "sh": ["Mediji", "Slika", "Медија", "Datoteka", "Medija", "Слика"],
    "si": ["රූපය", "මාධ්‍යය", "ගොනුව"],
    "sk": ["Súbor", "Obrázok", "Médiá"],
    "sl": ["Slika", "Datoteka"],
    "sq": ["Figura", "Skeda"],
    "sr": ["Датотека", "Medij", "Slika", "Медија", "Datoteka", "Медиј", "Medija", "Слика"],
    "srn": ["Afbeelding", "Gefre"],
    "stq": ["Bielde", "Bild"],
    "su": ["Média", "Gambar"],
    "sv": ["Fil", "Bild"],
    "sw": ["Faili", "Picha"],
    "szl": ["Plik", "Grafika"],
    "ta": ["படிமம்", "ஊடகம்"],
    "tcy": ["ಮಾದ್ಯಮೊ", "ಫೈಲ್"],
    "te": ["ఫైలు", "దస్త్రం", "బొమ్మ", "మీడియా"],
    "tet": ["Imajen", "Arquivo", "Imagem"],
    "tg": ["Акс", "Медиа"],
    "th": ["ไฟล์", "สื่อ", "ภาพ"],
    "ti": ["ፋይል", "ሜድያ"],
    "tk": ["Faýl"],
    "tl": ["Midya", "Talaksan"],
    "tpi": ["Fail"],
    "tr": ["Medya", "Resim", "Dosya", "Ortam"],
    "tt": ["Медиа", "Рәсем", "Файл", "Räsem", "Изображение"],
    "ty": ["Média", "Fichier"],
    "tyv": ["Медиа", "Файл", "Изображение"],
    "udm": ["Медиа", "Файл", "Суред", "Изображение"],
    "ug": ["ۋاسىتە", "ھۆججەت"],
    "uk": ["Медіа", "Медиа", "Файл", "Изображение", "Зображення"],
    "ur": ["میڈیا", "تصویر", "وسیط", "زریعہ", "فائل", "ملف"],
    "uz": ["Mediya", "Tasvir", "Fayl"],
    "vec": ["Immagine", "Imàjine", "Mèdia"],
    "vep": ["Pilt", "Fail"],
    "vi": ["Phương_tiện", "Tập_tin", "Hình", "Tập tin", "Phương tiện"],
    "vls": ["Afbeelding", "Ofbeeldienge"],
    "vo": ["Ragiv", "Magod", "Nünamakanäd"],
    "wa": ["Imådje"],
    "war": ["Medya", "Fayl", "Paypay"],
    "wo": ["Xibaarukaay", "Dencukaay"],
    "wuu": ["文件", "档案", "图像", "媒体"],
    "xal": ["Аһар", "Боомг", "Изображение", "Зург"],
    "xmf": ["მედია", "სურათი", "ფაილი"],
    "yi": ["מעדיע", "תמונה", "טעקע", "בילד"],
    "yo": ["Fáìlì", "Amóhùnmáwòrán", "Àwòrán"],
    "za": ["媒体文件", "文件", "档案", "图像", "媒体"],
    "zea": ["Afbeelding", "Plaetje"],
    "zh": ["媒体文件", "F", "文件", "媒體", "档案", "图像", "圖像", "媒体", "檔案"],
    "zh-classical": ["文件", "媒體", "圖像", "檔案"],
    "zh-min-nan": ["tóng-àn", "文件", "媒體", "Mûi-thé", "圖像", "檔案"],
    "zh-yue": ["檔", "档", "文件", "图", "媒體", "圖", "档案", "图像", "圖像", "媒体", "檔案"],
}

CAT_ALIASES = {
    "ab": ["Категория", "Акатегориа"],
    "ace": ["Kawan", "Kategori"],
    "af": ["Kategorie"],
    "ak": ["Nkyekyem"],
    "als": ["Kategorie"],
    "am": ["መደብ"],
    "an": ["Categoría"],
    "ang": ["Flocc"],
    "ar": ["تصنيف"],
    "arc": ["ܣܕܪܐ"],
    "arz": ["تصنيف"],
    "as": ["CAT", "শ্ৰেণী", "श्रेणी", "শ্রেণী"],
    "ast": ["Categoría"],
    "atj": ["Tipanictawin"],
    "av": ["Категория"],
    "ay": ["Categoría"],
    "az": ["Kateqoriya"],
    "azb": ["بؤلمه"],
    "ba": ["Төркөм", "Категория"],
    "bar": ["Kategorie"],
    "bat-smg": ["Kategorija", "Kateguorėjė"],
    "bcl": ["Kategorya"],
    "be": ["Катэгорыя"],
    "be-x-old": ["Катэгорыя"],
    "bg": ["Категория"],
    "bh": ["श्रेणी"],
    "bjn": ["Tumbung", "Kategori"],
    "bm": ["Catégorie"],
    "bn": ["বিষয়শ্রেণী", "വിഭാഗം"],
    "bpy": ["থাক"],
    "br": ["Rummad"],
    "bs": ["Kategorija"],
    "bug": ["Kategori"],
    "bxr": ["Категори", "Категория"],
    "ca": ["Categoria"],
    "cbk-zam": ["Categoría"],
    "cdo": ["分類"],
    "ce": ["Категори", "Тоба", "Кадегар"],
    "ceb": ["Kategoriya"],
    "ch": ["Katigoria"],
    "ckb": ["پ", "پۆل"],
    "co": ["Categoria"],
    "crh": ["Категория", "Kategoriya"],
    "cs": ["Kategorie"],
    "csb": ["Kategòrëjô"],
    "cu": ["Катигорї", "Категория", "Катигорїꙗ"],
    "cv": ["Категори"],
    "cy": ["Categori"],
    "da": ["Kategori"],
    "de": ["Kategorie"],
    "din": ["Bekätakthook"],
    "diq": ["Kategoriye", "Kategori"],
    "dsb": ["Kategorija"],
    "dty": ["श्रेणी"],
    "dv": ["ޤިސްމު"],
    "el": ["Κατηγορία"],
    "eml": ["Categoria"],
    "eo": ["Kategorio"],
    "es": ["CAT", "Categoría"],
    "et": ["Kategooria"],
    "eu": ["Kategoria"],
    "ext": ["Categoría", "Categoria"],
    "fa": ["رده"],
    "ff": ["Catégorie"],
    "fi": ["Luokka"],
    "fiu-vro": ["Katõgooria"],
    "fo": ["Bólkur"],
    "fr": ["Catégorie"],
    "frp": ["Catègorie"],
    "frr": ["Kategorie"],
    "fur": ["Categorie"],
    "fy": ["Kategory"],
    "ga": ["Rang", "Catagóir"],
    "gag": ["Kategori", "Kategoriya"],
    "gan": ["分類", "分类"],
    "gd": ["Roinn-seòrsa"],
    "gl": ["Categoría"],
    "glk": ["جرگه", "رده"],
    "gn": ["Ñemohenda"],
    "gom": ["वर्ग", "श्रेणी"],
    "gor": ["Dalala"],
    "got": ["𐌷𐌰𐌽𐍃𐌰"],
    "gu": ["શ્રેણી", "CAT", "શ્રે"],
    "gv": ["Ronney"],
    "hak": ["分類"],
    "haw": ["Māhele"],
    "he": ["קטגוריה", "קט"],
    "hi": ["श्र", "श्रेणी"],
    "hif": ["vibhag"],
    "hr": ["CT", "KT", "Kategorija"],
    "hsb": ["Kategorija"],
    "ht": ["Kategori"],
    "hu": ["Kategória"],
    "hy": ["Կատեգորիա"],
    "ia": ["Categoria"],
    "id": ["Kategori"],
    "ie": ["Categorie"],
    "ig": ["Ébéonọr", "Òtù"],
    "ii": ["分类"],
    "ilo": ["Kategoria"],
    "inh": ["ОагӀат"],
    "io": ["Kategorio"],
    "is": ["Flokkur"],
    "it": ["CAT", "Categoria"],
    "ja": ["カテゴリ"],
    "jbo": ["klesi"],
    "jv": ["Kategori"],
    "ka": ["კატეგორია"],
    "kaa": ["Sanat", "Kategoriya", "Санат", "سانات"],
    "kab": ["Taggayt"],
    "kbd": ["Категория", "Категориэ"],
    "kbp": ["Catégorie"],
    "kg": ["Kalasi"],
    "kk": ["Sanat", "Санат", "سانات"],
    "kl": ["Sumut_atassuseq", "Kategori", "Sumut atassuseq"],
    "km": ["ចំនាត់ថ្នាក់ក្រុម", "ចំណាត់ក្រុម", "ចំណាត់ថ្នាក់ក្រុម"],
    "kn": ["ವರ್ಗ"],
    "ko": ["분류"],
    "koi": ["Категория"],
    "krc": ["Категория"],
    "ks": ["زٲژ"],
    "ksh": ["Saachjropp", "Saachjrop", "Katejori", "Kategorie", "Saachjrupp", "Kattejori", "Sachjrop"],
    "ku": ["Kategorî", "پۆل"],
    "kv": ["Категория"],
    "kw": ["Class", "Klass"],
    "ky": ["Категория"],
    "la": ["Categoria"],
    "lad": ["Kateggoría", "Katēggoría", "Categoría"],
    "lb": ["Kategorie"],
    "lbe": ["Категория"],
    "lez": ["Категория"],
    "lfn": ["Categoria"],
    "li": ["Categorie", "Kategorie"],
    "lij": ["Categorîa", "Categoria"],
    "lmo": ["Categuria", "Categoria"],
    "ln": ["Catégorie"],
    "lo": ["ໝວດ"],
    "lrc": ["دأسە"],
    "lt": ["Kategorija"],
    "ltg": ["Kategoreja"],
    "lv": ["Kategorija"],
    "mai": ["CA", "श्रेणी"],
    "map-bms": ["Kategori"],
    "mdf": ["Категорие", "Категория"],
    "mg": ["Sokajy", "Catégorie"],
    "mhr": ["Категория", "Категорий"],
    "min": ["Kategori"],
    "mk": ["Категорија"],
    "ml": ["വിഭാഗം", "വി", "വർഗ്ഗം", "വ"],
    "mn": ["Ангилал"],
    "mr": ["वर्ग"],
    "mrj": ["Категори", "Категория"],
    "ms": ["Kategori"],
    "mt": ["Kategorija"],
    "mwl": ["Catadorie", "Categoria"],
    "my": ["ကဏ္ဍ"],
    "myv": ["Категория"],
    "mzn": ["رج", "رده"],
    "nah": ["Neneuhcāyōtl", "Categoría"],
    "nap": ["Categurìa", "Categoria"],
    "nds": ["Kategorie"],
    "nds-nl": ["Categorie", "Kattegerie", "Kategorie"],
    "ne": ["श्रेणी"],
    "new": ["पुचः"],
    "nl": ["Categorie"],
    "nn": ["Kategori"],
    "no": ["Kategori"],
    "nrm": ["Catégorie"],
    "nso": ["Setensele"],
    "nv": ["Tʼááłáhági_átʼéego", "Tʼááłáhági átʼéego"],
    "oc": ["Categoria"],
    "olo": ["Kategourii"],
    "or": ["ବିଭାଗ", "ଶ୍ରେଣୀ"],
    "os": ["Категори"],
    "pa": ["ਸ਼੍ਰੇਣੀ"],
    "pcd": ["Catégorie"],
    "pdc": ["Abdeeling", "Kategorie"],
    "pfl": ["Kadegorie", "Sachgrubb", "Kategorie"],
    "pi": ["विभाग"],
    "pl": ["Kategoria"],
    "pms": ["Categorìa"],
    "pnb": ["گٹھ"],
    "pnt": ["Κατηγορίαν"],
    "ps": ["وېشنيزه"],
    "pt": ["Categoria"],
    "qu": ["Katiguriya"],
    "rm": ["Categoria"],
    "rmy": ["Shopni"],
    "ro": ["Categorie"],
    "roa-rup": ["Categorie"],
    "roa-tara": ["Categoria"],
    "ru": ["Категория", "К"],
    "rue": ["Категория", "Катеґорія"],
    "rw": ["Ikiciro"],
    "sa": ["वर्गः"],
    "sah": ["Категория"],
    "sat": ["ᱛᱷᱚᱠ"],
    "sc": ["Categoria"],
    "scn": ["Catigurìa"],
    "sd": ["زمرو"],
    "se": ["Kategoriija"],
    "sg": ["Catégorie"],
    "sh": ["Kategorija", "Категорија"],
    "si": ["ප්‍රවර්ගය"],
    "sk": ["Kategória"],
    "sl": ["Kategorija"],
    "sq": ["Kategoria", "Kategori"],
    "sr": ["Kategorija", "Категорија"],
    "srn": ["Categorie", "Guru"],
    "stq": ["Kategorie"],
    "su": ["Kategori"],
    "sv": ["Kategori"],
    "sw": ["Jamii"],
    "szl": ["Kategoryjo", "Kategoria"],
    "ta": ["பகுப்பு"],
    "tcy": ["ವರ್ಗೊ"],
    "te": ["వర్గం"],
    "tet": ["Kategoría", "Kategoria"],
    "tg": ["Гурӯҳ"],
    "th": ["หมวดหมู่"],
    "ti": ["መደብ"],
    "tk": ["Kategoriýa"],
    "tl": ["Kategorya", "Kaurian"],
    "tpi": ["Grup"],
    "tr": ["Kategori", "KAT"],
    "tt": ["Төркем", "Törkem", "Категория"],
    "ty": ["Catégorie"],
    "tyv": ["Аңгылал", "Категория"],
    "udm": ["Категория"],
    "ug": ["تۈر"],
    "uk": ["Категория", "Категорія"],
    "ur": ["زمرہ"],
    "uz": ["Turkum", "Kategoriya"],
    "vec": ["Categoria"],
    "vep": ["Kategorii"],
    "vi": ["Thể_loại", "Thể loại"],
    "vls": ["Categorie"],
    "vo": ["Klad"],
    "wa": ["Categoreye"],
    "war": ["Kaarangay"],
    "wo": ["Wàll", "Catégorie"],
    "wuu": ["分类"],
    "xal": ["Янз", "Әәшл"],
    "xmf": ["კატეგორია"],
    "yi": ["קאטעגאריע", "קאַטעגאָריע"],
    "yo": ["Ẹ̀ka"],
    "za": ["分类"],
    "zea": ["Categorie"],
    "zh": ["分类", "分類", "CAT"],
    "zh-classical": ["分類", "CAT"],
    "zh-min-nan": ["分類", "Lūi-pia̍t"],
    "zh-yue": ["分类", "分類", "类", "類"],
}

__dir__ = os.path.dirname(__file__)

# load in app user-agent or any other app config
app.config.update(
    yaml.safe_load(open(os.path.join(__dir__, 'flask_config.yaml'))))

# Enable CORS for API endpoints
cors = CORS(app, resources={r'/api/*': {'origins': '*'}})


@app.route('/api/v1/quality-article', methods=['GET'])
def quality_article():
    lang, title, error = validate_api_args()
    if error:
        return jsonify({'error': error})
    quality, _ = get_quality(lang, title=title)
    return jsonify({'lang': lang, 'title': title, 'quality': quality,
                    'class': qual_score_to_class(quality)})

@app.route('/api/v1/quality-revid', methods=['GET'])
@app.route('/api/v1/quality-revid-features', methods=['GET'])
def quality_revid():
    lang, revid, error = validate_revid_api_args()
    if error:
        return jsonify({'error': error})
    quality, features = get_quality(lang, revid=revid)
    return jsonify({'lang': lang, 'revid': revid, 'quality': quality,
                    'class': qual_score_to_class(quality), 'features': features})

@app.route('/api/v1/quality-revid-compare', methods=['GET'])
def quality_revid_compare():
    lang, revid, error = validate_revid_api_args()
    if error:
        return jsonify({'error': error})
    wikitext_quality, _ = get_quality(lang, revid=revid)
    html_ord_score, html_ord_label, _ = get_html_predictions(lang, revid)
    return jsonify({'lang': lang, 'revid': revid,
                    'quality-wikitext': wikitext_quality, 'class-wikitext': qual_score_to_class(wikitext_quality),
                    'quality-html-ordinal': html_ord_score, 'class-html-ordinal': html_ord_label
                    })

@app.route('/api/v1/quality-revid-html', methods=['GET'])
def quality_revid_html():
    lang, revid, error = validate_revid_api_args()
    if error:
        return jsonify({'error': error})
    html_ord_score, html_ord_label, features = get_html_predictions(lang, revid)
    return jsonify({'lang': lang, 'revid': revid,
                    'quality-score': html_ord_score, 'quality-class': html_ord_label,
                    'features': features
                    })

@app.route('/api/v1/quality-article-features', methods=['GET'])
def quality_article_features():
    lang, title, error = validate_api_args()
    if error:
        return jsonify({'error': error})
    quality, features = get_quality(lang, title=title)
    return jsonify({'lang': lang, 'title': title, 'quality': quality,
                    'class': qual_score_to_class(quality), 'features': features})


def wikitext_to_features(wikitext, lang='en', level=3):
    """Gather counts of article components directly from wikitext.

    Pros:
    * Regex is much faster than mwparserfromhell (10x speed-up in testing) -- e.g., 200 µs vs. 2 ms for medium-sized article
    * Extended to catch some edge-cases -- e.g., images added via infoboxes/galleries that lack bracket syntax

    Cons/Issues:
    * Misses intra-nested links:
        * e.g. [[File:Image.jpg|Image with a [[caption]]]] only catches the File and not the [[caption]]
        * Could be extended by also regexing each link found, which should catch almost all, but more costly
    * Misses references added via templates w/o ref tags -- e.g., shortened-footnote templates.
    """
    try:
        cat_prefixes = [c.lower() for c in CAT_PREFIXES + CAT_ALIASES.get(lang, [])]
        med_prefixes = [m.lower() for m in MEDIA_PREFIXES + MEDIA_ALIASES.get(lang, [])]
        ref_singleton = re.compile(r'<ref(\s[^/>]*)?/>', re.M | re.I)
        ref_tag = re.compile(r'<ref(\s[^/>]*)?>[\s\S]*?</ref>', re.M | re.I)
        # remove comments / lowercase for matching namespace prefixes better
        wikitext = re.sub(r'<!--.*?-->', '', wikitext, flags=re.DOTALL).lower()

        page_length = len(wikitext)
        num_refs = len(ref_singleton.findall(wikitext)) + len(ref_tag.findall(wikitext))
        num_headings = len([1 for l in re.findall('(={2,})(.*?)(={2,})', wikitext) if len(l[0]) <= level])
        links = [m.split('|', maxsplit=1)[0] for m in re.findall(r'(?<=\[\[)(.*?)(?=]])', wikitext, flags=re.DOTALL)]
        num_categories = 0
        media_bra = []
        for l in links:
            if ':' in l:
                prefix, link_dest = l.split(':', maxsplit=1)
                if prefix in cat_prefixes:
                    num_categories += 1
                elif prefix in med_prefixes:
                    media_bra.append(link_dest)
        num_wikilinks = len(links) - num_categories - len(media_bra)
        media_ext = [''.join(m).strip() for m in EXTEN_PATTERN.findall(wikitext) if len(m[0]) <= 240]
        num_media = len(set(media_bra).union(set(media_ext)))

        return (page_length, num_refs, num_wikilinks, num_categories, num_media, num_headings)
    except Exception:
        return (0,0,0,0,0,0)

def qual_score_to_class(score):
    if score > 0 and score <= 0.42:
        return 'Stub'
    elif score <= 0.56:
        return 'Start'
    elif score <= 0.73:
        return 'C'
    elif score <= 0.85:
        return 'B'
    elif score <= 0.93:
        return 'GA'
    elif score <= 1:
        return 'FA'
    else:
        return None

def get_quality(lang, title=None, revid=None):
    """Get quality score for a given article (current version) or revision."""
    session = mwapi.Session(f'https://{lang}.wikipedia.org', user_agent=app.config['CUSTOM_UA'])

    # get wikitext for article
    if title is not None:
        result = session.get(
            action="parse",
            page=title,
            redirects='',
            prop='wikitext',
            format='json',
            formatversion=2
        )
    elif revid is not None:
        result = session.get(
            action="parse",
            oldid=revid,
            prop='wikitext',
            format='json',
            formatversion=2
        )
    else:
        raise Exception("Must pass either title or revision ID to quality function.")
    try:
        wikitext = result['parse']['wikitext']
        page_length, refs, wikilinks, categories, media, headings = wikitext_to_features(wikitext, lang)

        normed_page_length = math.sqrt(page_length)
        length_x = min(1, normed_page_length / MAX_QUAL_VALS[lang]['l'])
        media_x = min(1, media / MAX_QUAL_VALS[lang]['m'])
        categories_x = min(1, categories / MAX_QUAL_VALS[lang]['c'])
        refs_x = min(1, (refs / normed_page_length) / MAX_QUAL_VALS[lang]['r'])
        headings_x = min(1, (headings / normed_page_length) / MAX_QUAL_VALS[lang]['h'])
        wikilinks_x = min(1, (math.sqrt(wikilinks) / normed_page_length) / MAX_QUAL_VALS[lang]['w'])
        quality = ((COEF_LEN * length_x) + (COEF_MED * media_x) + (COEF_HEA * headings_x) +
                   (COEF_REF * refs_x) + (COEF_LIN * wikilinks_x) + (COEF_CAT * categories_x))
        return quality, {'raw':{'length (bytes)':page_length, 'references':refs, 'wikilinks':wikilinks,
                                'categories':categories, 'media':media, 'headings':headings},
                         'normalized':{'length (bytes)':length_x, 'references':refs_x, 'wikilinks':wikilinks_x,
                                       'categories':categories_x, 'media':media_x, 'headings':headings_x}}
    except Exception:
        traceback.print_exc()
        return -1, {'raw': {'length (bytes)': -1, 'references': -1, 'wikilinks': -1,
                                 'categories': -1, 'media': -1, 'headings': -1},
                         'normalized': {'length (bytes)': -1, 'references': -1, 'wikilinks': -1,
                                        'categories': -1, 'media': -1, 'headings': -1}}

def get_canonical_page_title(title, lang):
    """Resolve redirects / normalization -- used to verify that an input page_title exists"""
    session = mwapi.Session('https://{0}.wikipedia.org'.format(lang), user_agent=app.config['CUSTOM_UA'])

    result = session.get(
        action="query",
        prop="info",
        inprop='',
        redirects='',
        titles=title,
        format='json',
        formatversion=2
    )
    if 'missing' in result['query']['pages'][0]:
        return None
    else:
        return result['query']['pages'][0]['title'].replace(' ', '_')

def validate_lang(lang):
    return lang in WIKIPEDIA_LANGUAGE_CODES

def validate_revid(revid):
    try:
        revid = int(revid)
        return revid > 0
    except Exception:
        return False

def validate_api_args():
    """Validate API arguments for language-agnostic model."""
    error = None
    lang = None
    page_title = None
    if request.args.get('title') and request.args.get('lang'):
        lang = request.args['lang']
        page_title = get_canonical_page_title(request.args['title'], lang)
        if page_title is None:
            error = 'no matching article for <a href="https://{0}.wikipedia.org/wiki/{1}">https://{0}.wikipedia.org/wiki/{1}</a>'.format(lang, request.args['title'])
    elif request.args.get('lang'):
        error = 'missing an article title -- e.g., "2005_World_Series" for <a href="https://en.wikipedia.org/wiki/2005_World_Series">https://en.wikipedia.org/wiki/2005_World_Series</a>'
    elif request.args.get('title'):
        error = 'missing a language -- e.g., "en" for English'
    else:
        error = 'missing language -- e.g., "en" for English -- and title -- e.g., "2005_World_Series" for <a href="https://en.wikipedia.org/wiki/2005_World_Series">https://en.wikipedia.org/wiki/2005_World_Series</a>'

    return lang, page_title, error

def validate_revid_api_args():
    """Validate API arguments for language-agnostic model."""
    error = None
    lang = None
    revid = None
    if request.args.get('revid') and request.args.get('lang'):
        lang = request.args['lang']
        revid = request.args.get('revid')
        if not validate_revid(revid):
            error = f'invalid revision ID: {revid}'
    elif request.args.get('lang'):
        error = 'missing a revision ID -- e.g., "204134947" for <a href="https://en.wikipedia.org/w/index.php?oldid=204134947">https://en.wikipedia.org/w/index.php?oldid=204134947</a>'
    elif request.args.get('revid'):
        error = 'missing a language -- e.g., "en" for English'
    else:
        error = 'missing language -- e.g., "en" for English -- and revid -- e.g., "204134947" for <a href="https://en.wikipedia.org/w/index.php?oldid=204134947">https://en.wikipedia.org/w/index.php?oldid=204134947</a>'

    return lang, revid, error

def load_quality_maxvals():
    maxval_url = 'https://analytics.wikimedia.org/published/datasets/one-off/isaacj/misalignment/quality-max-featurevalues-by-wiki.tsv.gz'
    if not os.path.exists(MQV_FN):
        urlretrieve(maxval_url, MQV_FN)
    expected_header = ['wiki_db', 'num_pages', 'max_length', 'max_media', 'max_cats', 'max_refs', 'max_headings', 'max_links']
    wiki_idx = expected_header.index('wiki_db')
    len_idx = expected_header.index('max_length')
    hea_idx = expected_header.index('max_headings')
    ref_idx = expected_header.index('max_refs')
    med_idx = expected_header.index('max_media')
    cat_idx = expected_header.index('max_cats')
    lin_idx = expected_header.index('max_links')
    with gzip.open(MQV_FN, 'rt') as fin:
        header = next(fin).strip().split('\t')
        assert header == expected_header
        for line in fin:
            line = line.strip().split('\t')
            lang = line[wiki_idx].replace('wiki', '')
            if lang not in WIKIPEDIA_LANGUAGE_CODES:
                continue
            page_length = float(line[len_idx])
            headings = float(line[hea_idx])
            refs = float(line[ref_idx])
            media = float(line[med_idx])
            cats = float(line[cat_idx])
            links = float(line[lin_idx])
            MAX_QUAL_VALS[lang] = {'l':max(MIN_MAX_LEN, page_length),
                                   'm':max(MIN_MAX_MED, media),
                                   'r':max(MIN_MAX_REF, refs),
                                   'h':max(MIN_MAX_HEA, headings),
                                   'c':max(MIN_MAX_CAT, cats),
                                   'w':max(MIN_MAX_LIN, links)}

HTML_MAX_QUAL_VALS = {}

def get_html_predictions(lang, revid):
    article_html = get_article_html(lang, revid)
    if article_html is not None:
        page_length, refs, wikilinks, categories, media, headings, sources, infoboxes, messageboxes = get_article_features(article_html)
        if page_length > 0:
            length_x, refs_x, wikilinks_x, categories_x, media_x, headings_x, sources_x, infoboxes_x, messageboxes_x = normalize_features(lang, page_length, refs, wikilinks, categories, media, headings, sources, infoboxes, messageboxes)
            html_ord_score = (6.309 * length_x) + (1.198 * refs_x) + (0.647 * wikilinks_x) + (0.113 * categories_x) + (0.932 * media_x) + (0.292 * headings_x) + (0.174 * sources_x) + (0.344 * infoboxes_x) + (-0.946 * messageboxes_x)
            thresholds = [4.27085935, 7.10500962, 8.64130528, 9.70745503, 10.8792825]
            t_labels = ['Stub', 'Start', 'C', 'B', 'GA', 'FA']
            max_prob = -1
            prev_prob = 0
            html_ord_label = None
            for i, t in enumerate(thresholds):
                logit = t - html_ord_score
                odds = math.e ** (logit)
                cum_prob = odds / (1 + odds)
                lab_prob = cum_prob - prev_prob
                if lab_prob > max_prob:
                    max_prob = lab_prob
                    html_ord_label = t_labels[i]
                prev_prob = cum_prob
            if 1 - cum_prob > max_prob:
                html_ord_label = t_labels[-1]  # FA

            html_ord_score = 11.009 - html_ord_score
            html_ord_score = 1 - math.log(html_ord_score, 10.9541)

            features = {
                'raw':{
                    'length (bytes)':page_length, 'references':refs, 'wikilinks':wikilinks,
                    'categories':categories, 'media':media, 'headings':headings,
                    'sources':sources, 'infoboxes':infoboxes, 'messageboxes':messageboxes
                       },
                'normalized':{
                    'length (bytes)':length_x, 'references':refs_x, 'wikilinks':wikilinks_x,
                    'categories':categories_x, 'media':media_x, 'headings':headings_x,
                    'sources':sources_x, 'infoboxes':infoboxes_x, 'messageboxes':messageboxes_x
                    }
                }
            return (html_ord_score, html_ord_label, features)

    return (None, None, None)
    


def get_lin_prob(r, params):
    lin_prob = 0
    for var, coef in params.items():
        if var.endswith("_x"):
            lin_prob += coef * r[var]
    return lin_prob


def load_html_norm_vals():
    HTML_MIN_MAX_MED = 2
    HTML_MIN_MAX_CAT = 5
    HTML_MIN_MAX_LEN = 45 # changed from 100 to 45
    HTML_MIN_MAX_HEA = 0.1
    HTML_MIN_MAX_REF = 0.2  # changed from 0.15 to 0.2
    HTML_MIN_MAX_LIN = 0.45  # changed from 0.1 to 0.45
    HTML_MIN_MAX_UNIQUE_SOURCES = 5  # added sources
    maxval_url = 'https://analytics.wikimedia.org/published/datasets/one-off/isaacj/quality/V4-HTML/html-features-all-wikis-2024-07-01.tsv'
    mqf_fn = os.path.join(__dir__, 'html-quality-maxvals-by-wiki.tsv')
    if not os.path.exists(mqf_fn):
        urlretrieve(maxval_url, mqf_fn)    
    expected_header = ['wiki_db', 'num_pages', 'max_length', 'max_media', 'max_cats', 'max_refs', 'max_headings', 'max_links','max_srcs','infobox','mbox']
    wiki_idx = expected_header.index('wiki_db')
    len_idx = expected_header.index('max_length')
    hea_idx = expected_header.index('max_headings')
    ref_idx = expected_header.index('max_refs')
    med_idx = expected_header.index('max_media')
    cat_idx = expected_header.index('max_cats')
    lin_idx = expected_header.index('max_links')
    src_idx = expected_header.index('max_srcs')
    with open(mqf_fn, 'rt') as fin:
        header = next(fin).strip().split('\t')
        assert header == expected_header
        for line in fin:
            line = line.strip().split('\t')
            wiki = line[wiki_idx]
            lang = wiki.replace('wiki', '')
            page_length = float(line[len_idx])
            headings = float(line[hea_idx])
            refs = float(line[ref_idx])
            media = float(line[med_idx])
            cats = float(line[cat_idx])
            links = float(line[lin_idx])
            sources = float(line[src_idx])
            HTML_MAX_QUAL_VALS[lang] = {'l':max(HTML_MIN_MAX_LEN, page_length),
                                        'm':max(HTML_MIN_MAX_MED, media),
                                        'r':max(HTML_MIN_MAX_REF, refs),
                                        'h':max(HTML_MIN_MAX_HEA, headings),
                                        'c':max(HTML_MIN_MAX_CAT, cats),
                                        'w':max(HTML_MIN_MAX_LIN, links),
                                        's':max(HTML_MIN_MAX_UNIQUE_SOURCES, sources)}


def get_article_html(lang, revid):
    """Get an article revision's HTML."""
    base_url = f"https://{lang}.wikipedia.org/w/rest.php/v1/revision/{revid}/html" # returns the html contents
    try:
        response = requests.get(base_url, headers={'User-Agent': app.config['CUSTOM_UA']})
        return response.text
    except Exception:
        print("failed to fetch html")
        return None

def html_to_plaintext(article):
    """Convert Parsoid HTML to reasonable plaintext."""
    exclude_transcluded_paragraphs = True
    exclude_elements = {"Category", "Citation", "Comment", "Heading", 
                        "Infobox", "Math",
                        "Media-audio", "Media-img", "Media-video",
                        "Messagebox", "Navigational", "Note", "Reference",
                        "TF-sup",  # superscript -- catches Citation-needed tags etc.
                        "Table", "Wikitable"}
    exclude_para_context = {"pre-first-para", "between-paras", "post-last-para"}

    paragraphs = [paragraph.strip()
                  for heading, paragraph
                  in article.wikistew.get_plaintext(
                      exclude_transcluded_paragraphs=exclude_transcluded_paragraphs,
                      exclude_para_context=exclude_para_context,
                      exclude_elements=exclude_elements
                  )]
    
    return '\n'.join(paragraphs) if paragraphs else None


def get_article_features(article_html):
    try: 
        article = Article(article_html)
    except TypeError:
        print(f"Skipping article due to TypeError: {article_html}")
        return 0, 0, 0, 0, 0, 0, 0, 0, 0

    plaintext = html_to_plaintext(article)
    page_length = len(plaintext) if plaintext else 0
    refs = len(article.wikistew.get_citations())
    wikilinks = len([w for w in article.wikistew.get_wikilinks() if not is_transcluded(w.html_tag) and not w.redlink])
    categories = len([1 for c in article.wikistew.get_categories() if not is_transcluded(c.html_tag)])
    max_icon_pixel_area = 100*100 # 10000 pixels
    num_images = len([image for image in article.wikistew.get_images() if image.height * image.width > max_icon_pixel_area])
    num_videos = len([video for video in article.wikistew.get_video()])
    num_audio = len([audio for audio in article.wikistew.get_audio()])
    media = num_images + num_videos + num_audio
    headings = len([h for h in article.wikistew.get_headings() if h.level <= 3])
    sources = len(article.wikistew.get_references())
    has_infobox =  len(article.wikistew.get_infobox()) >= 1
    has_messagebox = len(article.wikistew.get_message_boxes()) >= 1
    
    return [page_length, refs, wikilinks, categories, media, headings, sources, has_infobox, has_messagebox]
    
    


def normalize_features(lang, page_length, num_refs, num_wikilinks, num_cats, num_media, num_headings, num_sources, has_infobox, has_messagebox):
    """Convert raw count features into values between 0 and 1.

    Possible transformations:
    * square root: make initial gains in feature of more importance to model
                   e.g., going from 0 -> 16 wikilinks is the same as 16 -> 64
    * divide by page length: convert absolutes to an expectation per byte of content
                             e.g., total references -> references per paragraph
    """
    normed_page_length = math.sqrt(page_length)
    length_x = min(1, normed_page_length / HTML_MAX_QUAL_VALS[lang]['l'])
    refs_x = min(1, (num_refs / normed_page_length) / HTML_MAX_QUAL_VALS[lang]['r'])
    wikilinks_x = min(1, (num_wikilinks / normed_page_length) / HTML_MAX_QUAL_VALS[lang]['w'])
    categories_x = min(1, num_cats / HTML_MAX_QUAL_VALS[lang]['c'])
    media_x = min(1, num_media / HTML_MAX_QUAL_VALS[lang]['m'])
    headings_x = min(1, (num_headings / normed_page_length) / HTML_MAX_QUAL_VALS[lang]['h'])
    sources_x = min(1, num_sources / HTML_MAX_QUAL_VALS[lang]['s'])
    infoboxes_x = has_infobox
    messageboxes_x = has_messagebox

    return length_x, refs_x, wikilinks_x, categories_x, media_x, headings_x , sources_x , infoboxes_x, messageboxes_x

load_html_norm_vals()
load_quality_maxvals()
application = app

if __name__ == '__main__':
    application.run()