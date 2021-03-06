""" XVM (c) https://modxvm.com 2013-2020 """

#####################################################################
# imports

import Math
import math
import traceback

import constants
import game
from constants import VISIBILITY
from account_helpers.settings_core.SettingsCore import SettingsCore
from account_helpers.settings_core import settings_constants
from Avatar import PlayerAvatar
from AvatarInputHandler.control_modes import PostMortemControlMode
from items.vehicles import VEHICLE_CLASS_TAGS
from gui.battle_control import avatar_getter
from gui.shared import g_eventBus, events
from gui.Scaleform.daapi.view.battle.shared.minimap.component import MinimapComponent
from gui.Scaleform.daapi.view.battle.shared.minimap.settings import ENTRY_SYMBOL_NAME, ADDITIONAL_FEATURES
from gui.Scaleform.daapi.view.battle.shared.minimap.plugins import ArenaVehiclesPlugin, PersonalEntriesPlugin

from xfw import *

from xvm_main.python.logger import *
from xvm_main.python.consts import *
import xvm_main.python.config as config

from battle import g_battle


#####################################################################
# constants

class XVM_ENTRY_SYMBOL_NAME(object):
    VEHICLE = 'com.xvm.battle.shared.minimap.entries.vehicle::UI_VehicleEntry'
    VIEW_POINT = 'com.xvm.battle.shared.minimap.entries.personal::UI_ViewPointEntry'
    DEAD_POINT = 'com.xvm.battle.shared.minimap.entries.personal::UI_DeadPointEntry'
    VIDEO_CAMERA = 'com.xvm.battle.shared.minimap.entries.personal::UI_VideoCameraEntry'
    ARCADE_CAMERA = 'com.xvm.battle.shared.minimap.entries.personal::UI_ArcadeCameraEntry'
    STRATEGIC_CAMERA = 'com.xvm.battle.shared.minimap.entries.personal::UI_StrategicCameraEntry'
    VIEW_RANGE_CIRCLES = 'com.xvm.battle.shared.minimap.entries.personal::UI_ViewRangeCirclesEntry'
    MARK_CELL = 'com.xvm.battle.shared.minimap.entries.personal::UI_CellFlashEntry'
    DEL_ENTRY_SYMBOLS = [VEHICLE, VIEW_POINT, DEAD_POINT, VIDEO_CAMERA,
                         ARCADE_CAMERA, STRATEGIC_CAMERA, VIEW_RANGE_CIRCLES, MARK_CELL]

#####################################################################
# initialization/finalization

def onConfigLoaded(self, e=None):
    g_minimap.enabled = config.get('minimap/enabled', True)
    g_minimap.opt_labelsEnabled = config.get('minimap/labelsEnabled', True)
    g_minimap.opt_linesEnabled = config.get('minimap/linesEnabled', True)
    g_minimap.opt_circlesEnabled = config.get('minimap/circlesEnabled', True)
    g_minimap.opt_minimapDeadSwitch = config.get('battle/minimapDeadSwitch', True)

g_eventBus.addListener(XVM_EVENT.CONFIG_LOADED, onConfigLoaded)

@registerEvent(game, 'fini')
def fini():
    g_eventBus.removeListener(XVM_EVENT.CONFIG_LOADED, onConfigLoaded)


######################################################################
## handlers

# Minimap

@overrideMethod(MinimapComponent, '_populate')
def _MinimapComponent_populate(base, self):
    g_minimap.init(self)
    base(self)

@overrideMethod(MinimapComponent, '_dispose')
def _MinimapComponent_dispose(base, self):
    g_minimap.destroy()
    base(self)

@overrideMethod(MinimapComponent, 'addEntry')
def _MinimapComponent_addEntry(base, self, symbol, *args, **kwargs):
    if g_minimap.active:
        if symbol == ENTRY_SYMBOL_NAME.VEHICLE:
            symbol = XVM_ENTRY_SYMBOL_NAME.VEHICLE
        elif symbol == ENTRY_SYMBOL_NAME.VIEW_POINT:
            symbol = XVM_ENTRY_SYMBOL_NAME.VIEW_POINT
        elif symbol == ENTRY_SYMBOL_NAME.DEAD_POINT:
            symbol = XVM_ENTRY_SYMBOL_NAME.DEAD_POINT
        elif symbol == ENTRY_SYMBOL_NAME.VIDEO_CAMERA:
            symbol = XVM_ENTRY_SYMBOL_NAME.VIDEO_CAMERA
        elif symbol == ENTRY_SYMBOL_NAME.ARCADE_CAMERA:
            symbol = XVM_ENTRY_SYMBOL_NAME.ARCADE_CAMERA
        elif symbol == ENTRY_SYMBOL_NAME.STRATEGIC_CAMERA:
            symbol = XVM_ENTRY_SYMBOL_NAME.STRATEGIC_CAMERA
        elif symbol == ENTRY_SYMBOL_NAME.VIEW_RANGE_CIRCLES:
            symbol = XVM_ENTRY_SYMBOL_NAME.VIEW_RANGE_CIRCLES
        elif symbol == ENTRY_SYMBOL_NAME.MARK_CELL:
            symbol = XVM_ENTRY_SYMBOL_NAME.MARK_CELL
        #else:
        #    debug('add minimap entry: ' + symbol)
    entryID = base(self, symbol, *args, **kwargs)
    if g_minimap.active:
        g_minimap.addEntry(entryID, symbol)
    return entryID

@overrideMethod(MinimapComponent, 'delEntry')
def _MinimapComponent_delEntry(base, self, entryID):
    if g_minimap.active:
        g_minimap.delEntry(entryID)
    base(self, entryID)

@overrideMethod(ArenaVehiclesPlugin, '_ArenaVehiclesPlugin__switchToVehicle')
def _ArenaVehiclesPlugin__switchToVehicle(base, self, prevCtrlID):
    base(self, prevCtrlID)
    if g_minimap.active and g_minimap.opt_labelsEnabled:
        if prevCtrlID != self._ctrlVehicleID:
            if prevCtrlID and prevCtrlID != self._getPlayerVehicleID() and prevCtrlID in self._entries:
                self._invoke(self._entries[prevCtrlID].getID(), 'xvm_setControlMode', False)
            if self._ctrlVehicleID:
                if self._ctrlVehicleID != self._getPlayerVehicleID() and self._ctrlVehicleID in self._entries:
                    self._invoke(self._entries[self._ctrlVehicleID].getID(), 'xvm_setControlMode', True)
                if g_minimap.viewPointID:
                    self._invoke(g_minimap.viewPointID, 'xvm_setVehicleID', self._ctrlVehicleID)

@overrideMethod(PersonalEntriesPlugin, '_PersonalEntriesPlugin__updateViewPointEntry')
def _PersonalEntriesPlugin__updateViewPointEntry(base, self, vehicleID=0):
    base(self, vehicleID)
    g_minimap.viewPointID = self._getViewPointID()


# Minimap dead switch

@overrideMethod(PostMortemControlMode, 'onMinimapClicked')
def _PostMortemControlMode_onMinimapClicked(base, self, worldPos):
    base(self, worldPos)
    #log('_PostMortemControlMode_onMinimapClicked active=' + str(g_minimap.active))
    if g_minimap.active and g_minimap.opt_minimapDeadSwitch:
        try:
            battle = getBattleApp()
            if not battle:
                return

            if isReplay() and not IS_DEVELOPMENT:
                return

            minDistance = None
            toID = None
            plugin = g_minimap.minimapComponent.getPlugin('vehicles')
            for vehicleID, entry in plugin._entries.iteritems():
                vData = avatar_getter.getArena().vehicles[vehicleID]
                if avatar_getter.getPlayerTeam() != vData['team'] or not vData['isAlive']:
                    continue
                matrix = entry.getMatrix()
                if matrix is not None:
                    pos = Math.Matrix(matrix).translation
                    distance = Math.Vector3(worldPos - pos).length
                    if minDistance is None or minDistance > distance:
                        minDistance = distance
                        toID = vehicleID
            if toID is not None:
                self.selectPlayer(toID)
        except Exception as ex:
            if IS_DEVELOPMENT:
                err(traceback.format_exc())


# Minimap settings

_CIRCLES_SETTINGS = (
    settings_constants.GAME.MINIMAP_DRAW_RANGE,
    settings_constants.GAME.MINIMAP_MAX_VIEW_RANGE,
    settings_constants.GAME.MINIMAP_VIEW_RANGE,
    settings_constants.GAME.SHOW_VEH_MODELS_ON_MAP)
_LINES_SETTINGS = (
    settings_constants.GAME.SHOW_VECTOR_ON_MAP,
    settings_constants.GAME.SHOW_SECTOR_ON_MAP)
_LABELS_SETTINGS = (
    settings_constants.GAME.SHOW_VEH_MODELS_ON_MAP)
_DEFAULTS = {
    settings_constants.GAME.SHOW_VECTOR_ON_MAP: False,
    settings_constants.GAME.SHOW_SECTOR_ON_MAP: True,
    settings_constants.GAME.MINIMAP_DRAW_RANGE: True,
    settings_constants.GAME.MINIMAP_MAX_VIEW_RANGE: True,
    settings_constants.GAME.MINIMAP_VIEW_RANGE: True,
    settings_constants.GAME.SHOW_VEH_MODELS_ON_MAP: False,
}

_in_PersonalEntriesPlugin_setSettings = False
_in_ArenaVehiclesPlugin_setSettings = False

@overrideMethod(SettingsCore, 'getSetting')
def _SettingsCore_getSetting(base, self, name):
    value = base(self, name)
    if g_minimap.active:
        global _in_PersonalEntriesPlugin_setSettings
        if _in_PersonalEntriesPlugin_setSettings:
            if name in _LINES_SETTINGS:
                if g_minimap.opt_linesEnabled:
                    value = _DEFAULTS[name]
            elif name in _CIRCLES_SETTINGS:
                if g_minimap.opt_circlesEnabled:
                    value = _DEFAULTS[name]
        global _in_ArenaVehiclesPlugin_setSettings
        if _in_ArenaVehiclesPlugin_setSettings:
            if name in _LABELS_SETTINGS:
                if g_minimap.opt_labelsEnabled:
                    value = _DEFAULTS[name]
        #debug('getSetting: {} = {}'.format(name, value))
    return value

@overrideMethod(PersonalEntriesPlugin, 'start')
def _PersonalEntriesPlugin_start(base, self):
    base(self)
    if g_minimap.active and g_minimap.opt_linesEnabled:
        if not self._PersonalEntriesPlugin__yawLimits:
            vehicle = avatar_getter.getArena().vehicles.get(avatar_getter.getPlayerVehicleID())
            staticTurretYaw = vehicle['vehicleType'].gun.staticTurretYaw
            if staticTurretYaw is None:
                vInfoVO = self._arenaDP.getVehicleInfo()
                yawLimits = vInfoVO.vehicleType.turretYawLimits
                if yawLimits:
                    self._PersonalEntriesPlugin__yawLimits = (math.degrees(yawLimits[0]), math.degrees(yawLimits[1]))

@overrideMethod(PersonalEntriesPlugin, 'setSettings')
def _PersonalEntriesPlugin_setSettings(base, self):
    global _in_PersonalEntriesPlugin_setSettings
    _in_PersonalEntriesPlugin_setSettings = True
    base(self)
    _in_PersonalEntriesPlugin_setSettings = False

@overrideMethod(PersonalEntriesPlugin, 'updateSettings')
def _PersonalEntriesPlugin_updateSettings(base, self, diff):
    if g_minimap.active:
        if g_minimap.opt_linesEnabled:
            if settings_constants.GAME.SHOW_VECTOR_ON_MAP in diff:
                diff[settings_constants.GAME.SHOW_VECTOR_ON_MAP] = _DEFAULTS[settings_constants.GAME.SHOW_VECTOR_ON_MAP]
            if settings_constants.GAME.SHOW_SECTOR_ON_MAP in diff:
                diff[settings_constants.GAME.SHOW_SECTOR_ON_MAP] = _DEFAULTS[settings_constants.GAME.SHOW_SECTOR_ON_MAP]
        if g_minimap.opt_circlesEnabled:
            if settings_constants.GAME.MINIMAP_DRAW_RANGE in diff:
                diff[settings_constants.GAME.MINIMAP_DRAW_RANGE] = _DEFAULTS[settings_constants.GAME.MINIMAP_DRAW_RANGE]
            if settings_constants.GAME.MINIMAP_MAX_VIEW_RANGE in diff:
                diff[settings_constants.GAME.MINIMAP_MAX_VIEW_RANGE] = _DEFAULTS[settings_constants.GAME.MINIMAP_MAX_VIEW_RANGE]
            if settings_constants.GAME.MINIMAP_VIEW_RANGE in diff:
                diff[settings_constants.GAME.MINIMAP_VIEW_RANGE] = _DEFAULTS[settings_constants.GAME.MINIMAP_VIEW_RANGE]
    base(self, diff)

@overrideMethod(ArenaVehiclesPlugin, 'setSettings')
def _ArenaVehiclesPlugin_setSettings(base, self):
    global _in_ArenaVehiclesPlugin_setSettings
    _in_ArenaVehiclesPlugin_setSettings = True
    base(self)
    _in_ArenaVehiclesPlugin_setSettings = False

@overrideMethod(ArenaVehiclesPlugin, 'updateSettings')
def _ArenaVehiclesPlugin_updateSettings(base, self, diff):
    if g_minimap.active:
        if g_minimap.opt_labelsEnabled:
            if settings_constants.GAME.SHOW_VEH_MODELS_ON_MAP in diff:
                diff[settings_constants.GAME.SHOW_VEH_MODELS_ON_MAP] = _DEFAULTS[settings_constants.GAME.SHOW_VEH_MODELS_ON_MAP]
    base(self, diff)


# Disable standard features if XVM minimap is active

@overrideClassMethod(ADDITIONAL_FEATURES, 'isOn')
def _ADDITIONAL_FEATURES_isOn(base, cls, mask):
    return False if g_minimap.active and g_minimap.opt_labelsEnabled else base(mask)

@overrideClassMethod(ADDITIONAL_FEATURES, 'isChanged')
def _ADDITIONAL_FEATURES_isChanged(base, cls, mask):
    return False if g_minimap.active and g_minimap.opt_labelsEnabled else base(mask)

@overrideMethod(PersonalEntriesPlugin, '_PersonalEntriesPlugin__onVehicleFeedbackReceived')
def _PersonalEntriesPlugin__onVehicleFeedbackReceived(base, self, eventID, _, value):
    if g_minimap.active and g_minimap.opt_circlesEnabled:
        VISIBILITY.MAX_RADIUS = 1000
        base(self, eventID, _, value)
        VISIBILITY.MAX_RADIUS = 445
    else:
        base(self, eventID, _, value)


#####################################################################
# Minimap

class _Minimap(object):

    enabled = True
    initialized = False
    guiType = 0
    battleType = 0
    opt_labelsEnabled = True
    opt_linesEnabled = True
    opt_circlesEnabled = True
    opt_minimapDeadSwitch = True
    viewPointID = 0
    minimapComponent = None
    entrySymbols = {}

    @property
    def active(self):
        #log('g_battle.xvm_battle_swf_initialized: ' + str(g_battle.xvm_battle_swf_initialized))
        return g_battle.xvm_battle_swf_initialized and \
               self.enabled and \
               self.initialized and \
               (self.guiType != constants.ARENA_GUI_TYPE.EPIC_BATTLE) and \
               (self.guiType != constants.ARENA_GUI_TYPE.TUTORIAL) and \
               (self.battleType != constants.ARENA_BONUS_TYPE.TUTORIAL)

    def init(self, minimapComponent):
        self.initialized = True
        arena = avatar_getter.getArena()
        self.guiType = arena.guiType
        self.battleType = arena.bonusType
        self.minimapComponent = minimapComponent
        self.entrySymbols = {}

    def addEntry(self, entryID, symbol):
        #log('addEntry: ' + str(entryID))
        self.entrySymbols[entryID] = symbol

    def delEntry(self, entryID):
        #log('delEntry: ' + str(entryID) + ' = ' + self.entrySymbols[entryID])
        symbol = self.entrySymbols.pop(entryID)
        if symbol in XVM_ENTRY_SYMBOL_NAME.DEL_ENTRY_SYMBOLS:
            try:
                self.minimapComponent.invoke(entryID, 'xvm_delEntry')
            except Exception as ex:
                err(traceback.format_exc())

    def destroy(self):
        if self.active:
            for entryID in self.entrySymbols.keys():
                self.delEntry(entryID)

        self.initialized = False
        self.minimapComponent = None

g_minimap = _Minimap()
