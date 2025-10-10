from mweb import MWebBase, MWebConfig, MWebSystemConfig
from mweb.engine.mweb_connector import MWebModule
from mweb.engine.mweb_data import MWebModuleDetails
from mweb.engine.mweb_hook import MWebHook
from mweb.engine.mweb_util import MWebUtil
from .common.mweb_builtin_config import MWebBuiltinConfig


class MWebBuiltinModule(MWebModule):
    def register_module(self) -> MWebModuleDetails:
        return MWebModuleDetails(systemName="mweb-builtin", displayName="MWeb Builtin")

    async def initialize(self, mweb_app: MWebBase, config: MWebConfig, hook: MWebHook, system_config: MWebSystemConfig, **kwargs):
        MWebUtil.copy_config_property(source=config, destination=MWebBuiltinConfig)

    def register_model(self, mweb_orm) -> list:
        pass

    def register_controller(self, mweb_app: MWebBase):
        pass

    async def run_on_start(self, mweb_app: MWebBase, config: MWebConfig):
        pass

    async def run_on_cli_init(self, mweb_app: MWebBase, config: MWebConfig):
        pass
