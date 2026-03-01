pkg install python310 py310-requests py310-pip py310-lxml py310-pillow py310-cloudscraper py310-pysocks git zip py310-beautifulsoup448 py310-mechanicalsoup
pip install pyinstaller
pyinstaller --onefile Movie_Data_Capture.py  --hidden-import ADC_function.py --hidden-import core.py \
    --hidden-import "ImageProcessing.cnn" \
    --python-option u \
    --add-data "$(python3.10 -c 'import cloudscraper as _; print(_.__path__[0])' | tail -n 1):cloudscraper" \
    --add-data "$(python3.10 -c 'import opencc as _; print(_.__path__[0])' | tail -n 1):opencc" \
    --add-data "$(python3.10 -c 'import face_recognition_models as _; print(_.__path__[0])' | tail -n 1):face_recognition_models" \
    --add-data "Img:Img" \
    --add-data "config.ini:." \

cp config.ini ./dist
