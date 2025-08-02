import base64
import enum
from io import BytesIO
import barcode
from dataclasses import dataclass
from barcode.writer import ImageWriter
from mw_common import SDLize
from mw_file_content import FileUtil
from mweb_builtin.barcode.bcode_svg_writer import BCodeSVGWriter


class BarcodeType(enum.Enum):
    CODE128 = "code128"
    EAN8 = "ean8"
    EAN13 = "ean13"
    PZN = "pzn"
    CODABAR = "codabar"


@dataclass(kw_only=True)
class BarcodeConfig(SDLize):
    module_width: float = 0.2
    module_height: float = 8.0
    quiet_zone: float = 0.5
    font_size: int = 6
    text_distance: float = 2.5
    background: str = "white"
    foreground: str = "black"
    write_text: bool = True
    margin_bottom: float = 0.0
    margin_top: float = 0.5
    human: str = None
    text_align: str = "middle"  # middle and start
    top_text: str = None
    top_text_distance: float = 1


class BarcodeUtil:

    @staticmethod
    def get_base64(code: str, code_type: BarcodeType = BarcodeType.CODE128):
        barcodeGenerator = barcode.get_barcode_class(code_type.value)
        barcode_data = barcodeGenerator(code, writer=ImageWriter())
        buffer = BytesIO()
        barcode_data.write(buffer)
        # "<img src="data:image/png;base64,{base64_image}" alt="{code}"/>"
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    @staticmethod
    def generate(code: str, file_path: str, file_name: str = None, config: BarcodeConfig = None, code_type: BarcodeType = BarcodeType.CODE128):
        barcodeGenerator = barcode.get_barcode_class(code_type.value)
        generator = barcodeGenerator(code, writer=BCodeSVGWriter())

        if not config:
            config = BarcodeConfig()

        options: dict = config.to_dict()

        if not file_name:
            file_name = f"{code}"

        FileUtil.create_directories(file_path)
        path_and_filename = FileUtil.join_path(file_path, file_name)
        FileUtil.delete(path_and_filename)
        generator.save(path_and_filename, options=options)
        return path_and_filename
