import qrcode
from qrcode.main import QRCode
from mw_file_content import FileUtil


class QRCodeUtil:

    @classmethod
    def generate(cls, data: str, file_path: str, filename: str, border: int = 1):
        qrcode_generator = QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=border,
        )

        qrcode_generator.add_data(data)
        qrcode_generator.make(fit=True)

        image = qrcode_generator.make_image(
            fill_color="black",
            back_color="white",
        )

        FileUtil.create_directories(file_path)
        saved_path = FileUtil.join_path(file_path, f"{filename}.png")
        image.save(saved_path)
