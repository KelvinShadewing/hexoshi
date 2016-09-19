#!/usr/bin/env python2

# Hexoshi
# Copyright (C) 2014-2016 onpon4 <onpon4@riseup.net>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import division
from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

__version__ = "1.1"

import argparse
import datetime
import gettext
import itertools
import json
import math
import os
import random
import shutil
import sys
import tempfile
import traceback
import warnings
import weakref
import zipfile

import sge
import six
import tmx
import xsge_gui
import xsge_lighting
import xsge_path
import xsge_physics
import xsge_tmx

try:
    from six.moves.tkinter import Tk
    # six.moves.tkinter_filedialog doesn't work correctly.
    if six.PY2:
        import tkFileDialog as tkinter_filedialog
    else:
        import tkinter.filedialog as tkinter_filedialog
except ImportError:
    HAVE_TK = False
else:
    HAVE_TK = True


if getattr(sys, "frozen", False):
    __file__ = sys.executable

DATA = tempfile.mkdtemp("hexoshi-data")
CONFIG = os.path.join(os.path.expanduser("~"), ".config", "hexoshi")

dirs = [os.path.join(os.path.dirname(__file__), "data"),
        os.path.join(CONFIG, "data")]
for d in dirs:
    if os.path.isdir(d):
        for dirpath, dirnames, filenames in os.walk(d, True, None, True):
            dirtail = os.path.relpath(dirpath, d)
            nd = os.path.join(DATA, dirtail)

            for dirname in dirnames:
                dp = os.path.join(nd, dirname)
                if not os.path.exists(dp):
                    os.makedirs(dp)

            for fname in filenames:
                shutil.copy2(os.path.join(dirpath, fname), nd)
del dirs

gettext.install("hexoshi", os.path.abspath(os.path.join(DATA, "locale")))

parser = argparse.ArgumentParser()
parser.add_argument(
    "-p", "--print-errors",
    help=_("Print errors directly to stdout rather than saving them in a file."),
    action="store_true")
parser.add_argument(
    "-l", "--lang",
    help=_("Manually choose a different language to use."))
parser.add_argument(
    "--nodelta",
    help=_("Disable delta timing. Causes the game to slow down when it can't run at full speed instead of becoming choppier."),
    action="store_true")
parser.add_argument(
    "-d", "--datadir",
    help=_('Where to load the game data from (Default: "{}")').format(DATA))
parser.add_argument(
    "--level",
    help=_("Play the indicated level and then exit."))
parser.add_argument(
    "--record",
    help=_("Start the indicated level and record player actions in a timeline. Useful for making cutscenes."))
parser.add_argument(
    "--no-backgrounds",
    help=_("Only show solid colors for backgrounds (uses less RAM)."),
    action="store_true")
parser.add_argument(
    "--no-hud", help=_("Don't show the player's heads-up display."),
    action="store_true")
parser.add_argument("--scale-basic", action="store_true")
parser.add_argument("--god")
args = parser.parse_args()

PRINT_ERRORS = args.print_errors
DELTA = not args.nodelta
if args.datadir:
    DATA = args.datadir
LEVEL = args.level
RECORD = args.record
NO_BACKGROUNDS = args.no_backgrounds
NO_HUD = args.no_hud
GOD = (args.god and args.god.lower() == "plz4giv")

if args.lang:
    lang = gettext.translation("hexoshi",
                               os.path.abspath(os.path.join(DATA, "locale")),
                               [args.lang])
    lang.install()

SCREEN_SIZE = [400, 224]
TILE_SIZE = 16
FPS = 56
DELTA_MIN = FPS / 2
DELTA_MAX = FPS * 4
TRANSITION_TIME = 750

GRAVITY = 0.2

PLAYER_MAX_HP = 100
PLAYER_MAX_SPEED = 3
PLAYER_ACCELERATION = 0.25
PLAYER_AIR_ACCELERATION = 0.1
PLAYER_FRICTION = 0.5
PLAYER_AIR_FRICTION = 0.01
PLAYER_JUMP_HEIGHT = 5 * TILE_SIZE + 2
PLAYER_FALL_SPEED = 4
PLAYER_SLIDE_SPEED = 0.5
PLAYER_RUN_FRAMES_PER_PIXEL = 1 / 10
PLAYER_HITSTUN = FPS
PLAYER_HITSTUN_SPEED = 0.5

CEILING_LAX = 2

CAMERA_HSPEED_FACTOR = 1 / 2
CAMERA_VSPEED_FACTOR = 1 / 20
CAMERA_OFFSET_FACTOR = 10
CAMERA_MARGIN_TOP = 4 * TILE_SIZE
CAMERA_MARGIN_BOTTOM = 5 * TILE_SIZE
CAMERA_TARGET_MARGIN_BOTTOM = CAMERA_MARGIN_BOTTOM + TILE_SIZE

SHAKE_FRAME_TIME = FPS / DELTA_MIN
SHAKE_AMOUNT = 3

TEXT_SPEED = 1000

SAVE_NSLOTS = 10
MENU_MAX_ITEMS = 14

SOUND_MAX_RADIUS = 200
SOUND_ZERO_RADIUS = 600
SOUND_CENTERED_RADIUS = 75
SOUND_TILTED_RADIUS = 500
SOUND_TILT_LIMIT = 0.75

backgrounds = {}
loaded_music = {}
tux_grab_sprites = {}

fullscreen = False
scale_method = None
sound_enabled = True
music_enabled = True
stereo_enabled = True
fps_enabled = False
joystick_threshold = 0.1
left_key = [["left", "a"]]
right_key = [["right", "d"]]
up_key = [["up", "w"]]
down_key = [["down", "s"]]
halt_key = [["alt_left", "alt_right"]]
jump_key = [["space"]]
shoot_key = [["ctrl_left", "ctrl_right"]]
aim_up_key = [["x"]]
aim_down_key = [["z"]]
mode_reset_key = [["shift_left", "shift_right"]]
mode_key = [["tab"]]
pause_key = [["enter", "p"]]
left_js = [[(0, "axis-", 0), (0, "hat_left", 0)]]
right_js = [[(0, "axis+", 0), (0, "hat_right", 0)]]
up_js = [[(0, "axis-", 1), (0, "hat_up", 0)]]
down_js = [[(0, "axis+", 1), (0, "hat_down", 0)]]
halt_js = [[(0, "button", 10), (0, "button", 11)]]
jump_js = [[(0, "button", 1), (0, "button", 3)]]
action_js = [[(0, "button", 0)]]
aim_up_js = [[(0, "button", 5), (0, "button", 7)]]
aim_down_js = [[(0, "button", 4), (0, "button", 6)]]
mode_reset_js = [[(0, "button", 2)]]
mode_js = [[(0, "button", 8)]]
pause_js = [[(0, "button", 9)]]
save_slots = [None for i in six.moves.range(SAVE_NSLOTS)]

abort = False

current_save_slot = None
current_levelset = None
start_cutscene = None
worldmap = None
loaded_worldmaps = {}
levels = []
loaded_levels = {}
level_names = {}
level_timers = {}
cleared_levels = []
tuxdolls_available = []
tuxdolls_found = []
watched_timelines = []
level_time_bonus = 0
current_worldmap = None
worldmap_entry_space = None
current_worldmap_space = None
current_level = 0
current_checkpoints = {}

score = 0

current_areas = {}
main_area = None
level_cleared = False
mapdest = None
mapdest_space = None


class Game(sge.dsp.Game):

    fps_time = 0
    fps_frames = 0
    fps_text = ""

    def event_step(self, time_passed, delta_mult):
        if fps_enabled:
            self.fps_time += time_passed
            self.fps_frames += 1
            if self.fps_time >= 250:
                self.fps_text = str(round(
                    (1000 * self.fps_frames) / self.fps_time, 2))
                self.fps_time = 0
                self.fps_frames = 0

            self.project_text(font_small, self.fps_text, self.width - 8,
                              self.height - 8, z=1000,
                              color=sge.gfx.Color("yellow"), halign="right",
                              valign="bottom")

    def event_key_press(self, key, char):
        global fullscreen

        if key == "f11":
            fullscreen = not fullscreen
            self.fullscreen = fullscreen

    def event_mouse_button_press(self, button):
        if button == "middle":
            self.event_close()

    def event_close(self):
        rush_save()
        self.end()

    def event_paused_close(self):
        self.event_close()


class Level(sge.dsp.Room):

    """Handles levels."""

    def __init__(self, objects=(), width=None, height=None, views=None,
                 background=None, background_x=0, background_y=0,
                 object_area_width=TILE_SIZE * 2,
                 object_area_height=TILE_SIZE * 2,
                 name=None, bgname=None, music=None,
                 time_bonus=DEFAULT_LEVEL_TIME_BONUS, spawn=None,
                 timeline=None, ambient_light=None, disable_lights=False,
                 persistent=True):
        self.fname = None
        self.name = name
        self.music = music
        self.time_bonus = time_bonus
        self.spawn = spawn
        self.persistent = persistent
        self.points = 0
        self.timeline_objects = {}
        self.warps = []
        self.shake_queue = 0
        self.pause_delay = TRANSITION_TIME
        self.game_won = False
        self.status_text = None

        if bgname is not None:
            background = backgrounds.get(bgname, background)

        self.load_timeline(timeline)

        if ambient_light:
            self.ambient_light = sge.gfx.Color(ambient_light)
            if (self.ambient_light.red >= 255 and
                    self.ambient_light.green >= 255 and
                    self.ambient_light.blue >= 255):
                self.ambient_light = None
        else:
            self.ambient_light = None

        self.disable_lights = disable_lights or self.ambient_light is None

        super(Level, self).__init__(objects, width, height, views, background,
                                    background_x, background_y,
                                    object_area_width, object_area_height)
        self.add(gui_handler)

    def load_timeline(self, timeline):
        self.timeline = {}
        self.timeline_name = ""
        self.timeline_step = 0
        self.timeline_skip_target = None
        if timeline:
            self.timeline_name = timeline
            fname = os.path.join(DATA, "timelines", timeline)
            with open(fname, 'r') as f:
                jt = json.load(f)

            for i in jt:
                self.timeline[eval(i)] = jt[i]

    def add_timeline_object(self, obj):
        if obj.ID is not None:
            self.timeline_objects[obj.ID] = weakref.ref(obj)

    def timeline_skipto(self, step):
        t_keys = sorted(self.timeline.keys())
        self.timeline_step = step
        while t_keys and t_keys[0] < step:
            i = t_keys.pop(0)
            self.timeline[i] = []

    def add_points(self, x):
        if main_area not in cleared_levels:
            self.points += x

    def show_hud(self):
        # Show darkness
        if self.ambient_light:
            xsge_lighting.project_darkness(ambient_light=self.ambient_light,
                                           buffer=TILE_SIZE * 2)
        else:
            xsge_lighting.clear_lights()

        if not NO_HUD:
            if self.points:
                score_text = "{}+{}".format(score, self.points)
            else:
                score_text = str(score)
            time_bonus = level_timers.get(main_area, 0)
            text = "{}\n{}\n\n{}\n{}".format(
                _("Score"), score_text,
                _("Time Bonus") if time_bonus >= 0 else _("Time Penalty"),
                abs(time_bonus))
            sge.game.project_text(font, text, sge.game.width / 2, 0,
                                  color=sge.gfx.Color("white"),
                                  halign="center")

            if main_area in tuxdolls_available or main_area in tuxdolls_found:
                if main_area in tuxdolls_found:
                    s = tuxdoll_sprite
                else:
                    s = tuxdoll_transparent_sprite
                sge.game.project_sprite(s, 0, sge.game.width / 2, font.size * 6)

            if self.status_text:
                sge.game.project_text(font, self.status_text,
                                      sge.game.width / 2, sge.game.height - 16,
                                      color=sge.gfx.Color("white"),
                                      halign="center", valign="middle")
                self.status_text = None

    def shake(self, num=1):
        shaking = (self.shake_queue or "shake_up" in self.alarms or
                   "shake_down" in self.alarms)
        self.shake_queue = max(self.shake_queue, num)
        if not shaking:
            self.event_alarm("shake_down")

        for obj in self.objects:
            if isinstance(obj, SteadyIcicle):
                obj.check_shake(True)

    def pause(self):
        global level_timers
        global score

        if self.death_time is not None or "death" in self.alarms:
            if level_timers.setdefault(main_area, 0) >= 0:
                sge.snd.Music.stop()
                self.alarms["death"] = 0
        elif (self.timeline_skip_target is not None and
              self.timeline_step < self.timeline_skip_target):
            self.timeline_skipto(self.timeline_skip_target)
        elif self.pause_delay <= 0 and not self.won:
            sge.snd.Music.pause()
            play_sound(pause_sound)
            PauseMenu.create()

    def die(self):
        global current_areas
        current_areas = {}
        self.death_time = DEATH_FADE_TIME
        self.death_time_bonus = level_timers.setdefault(main_area, 0)
        if "timer" in self.alarms:
            del self.alarms["timer"]
        sge.snd.Music.clear_queue()
        sge.snd.Music.stop(DEATH_FADE_TIME)

    def return_to_map(self, completed=False):
        global current_worldmap
        global current_worldmap_space
        global mapdest
        global mapdest_space

        if completed:
            if mapdest:
                current_worldmap = mapdest
            if mapdest_space:
                current_worldmap_space = mapdest_space
                worldmap_entry_space = mapdest_space

        mapdest = None
        mapdest_space = None

        save_game()
        if current_worldmap:
            m = Worldmap.load(current_worldmap)
            m.start(transition="iris_out", transition_time=TRANSITION_TIME)
        else:
            sge.game.start_room.start()

    def win_level(self, victory_walk=True):
        global current_checkpoints

        for obj in self.objects[:]:
            if isinstance(obj, WinPuffObject) and obj.active:
                obj.win_puff()

        for obj in self.objects:
            if isinstance(obj, Player):
                obj.human = False
                obj.left_pressed = False
                obj.right_pressed = False
                obj.up_pressed = False
                obj.down_pressed = False
                obj.jump_pressed = False
                obj.action_pressed = False
                obj.sneak_pressed = True
                obj.jump_release()

                if victory_walk:
                    if obj.xvelocity >= 0:
                        obj.right_pressed = True
                    else:
                        obj.left_pressed = True

        if "timer" in self.alarms:
            del self.alarms["timer"]

        self.won = True
        self.alarms["win_count_points"] = WIN_COUNT_START_TIME
        current_checkpoints[main_area] = None
        sge.snd.Music.clear_queue()
        sge.snd.Music.stop()
        if music_enabled:
            level_win_music.play()

    def win_game(self):
        global current_level
        current_level = 0
        save_game()
        credits_room = CreditsScreen.load(os.path.join("special",
                                                       "credits.tmx"))
        credits_room.start()

    def event_room_start(self):
        self.add(coin_animation)
        self.add(bonus_animation)
        self.add(lava_animation)
        self.add(goal_animation)

        self.event_room_resume()

    def event_room_resume(self):
        global main_area
        global level_time_bonus

        xsge_lighting.clear_lights()

        self.won = False
        self.win_count_points = False
        self.win_count_time = False
        self.death_time = None
        self.alarms["timer"] = TIMER_FRAMES
        self.pause_delay = TRANSITION_TIME
        play_music(self.music)

        if main_area is None:
            main_area = self.fname

        if main_area == self.fname:
            level_time_bonus = self.time_bonus

        if GOD:
            level_timers[main_area] = min(0, level_timers.get(main_area, 0))
        elif main_area not in level_timers:
            if main_area in levels:
                level_timers[main_area] = level_time_bonus
            else:
                level_timers[main_area] = 0

        players = []
        spawn_point = None

        for obj in self.objects:
            if isinstance(obj, (Spawn, Door, WarpSpawn)):
                if self.spawn is not None and obj.spawn_id == self.spawn:
                    spawn_point = obj

                if isinstance(obj, Warp) and obj not in self.warps:
                    self.warps.append(obj)
            elif isinstance(obj, Player):
                players.append(obj)

        del_warps = []
        for warp in self.warps:
            if warp not in self.objects:
                del_warps.append(warp)
        for warp in del_warps:
            self.warps.remove(warp)

        if spawn_point is not None:
            for player in players:
                player.x = spawn_point.x
                player.y = spawn_point.y
                if player.view is not None:
                    player.view.x = player.x - player.view.width / 2
                    player.view.y = (player.y - player.view.height +
                                     CAMERA_TARGET_MARGIN_BOTTOM)

                if isinstance(spawn_point, WarpSpawn):
                    player.visible = False
                    player.tangible = False
                    player.warping = True
                    spawn_point.follow_start(player, WARP_SPEED)
                else:
                    player.visible = True
                    player.tangible = True
                    player.warping = False

    def event_step(self, time_passed, delta_mult):
        global watched_timelines
        global level_timers
        global current_level
        global score
        global current_areas
        global main_area
        global level_cleared

        if self.pause_delay > 0:
            self.pause_delay -= time_passed

        # Handle inactive objects and lighting
        if self.ambient_light:
            range_ = max(ACTIVATE_RANGE, LIGHT_RANGE)
        else:
            range_ = ACTIVATE_RANGE

        for view in self.views:
            for obj in self.get_objects_at(
                    view.x - range_, view.y - range_, view.width + range_ * 2,
                    view.height + range_ * 2):
                if isinstance(obj, InteractiveObject):
                    if not self.disable_lights:
                        obj.project_light()

                if not obj.active:
                    if isinstance(obj, InteractiveObject):
                        obj.update_active()
                    elif isinstance(obj, (Lava, LavaSurface)):
                        obj.image_index = lava_animation.image_index
                    elif isinstance(obj, (Goal, GoalTop)):
                        obj.image_index = goal_animation.image_index

        # Show HUD
        self.show_hud()

        # Timeline events
        t_keys = sorted(self.timeline.keys())
        while t_keys:
            i = t_keys.pop(0)
            if i <= self.timeline_step:
                while i in self.timeline and self.timeline[i]:
                    command = self.timeline[i].pop(0)
                    command = command.split(None, 1)
                    if command:
                        if len(command) >= 2:
                            command, arg = command[:2]
                        else:
                            command = command[0]
                            arg = ""

                        if command.startswith("#"):
                            # Comment; do nothing
                            pass
                        elif command == "setattr":
                            args = arg.split(None, 2)
                            if len(args) >= 3:
                                obj, name, value = args[:3]

                                try:
                                    value = eval(value)
                                except Exception as e:
                                    m = _("An error occurred in a timeline 'setattr' command:\n\n{}").format(
                                    traceback.format_exc())
                                    show_error(m)
                                else:
                                    if obj in self.timeline_objects:
                                        obj = self.timeline_objects[obj]()
                                        if obj is not None:
                                            setattr(obj, name, value)
                                    elif obj == "__level__":
                                        setattr(self, name, value)
                        elif command == "call":
                            args = arg.split()
                            if len(args) >= 2:
                                obj, method = args[:2]
                                fa = [eval(s) for s in args[2:]]

                                if obj in self.timeline_objects:
                                    obj = self.timeline_objects[obj]()
                                    if obj is not None:
                                        getattr(obj, method, lambda: None)(*fa)
                                elif obj == "__level__":
                                    getattr(self, method, lambda: None)(*fa)
                        elif command == "dialog":
                            args = arg.split(None, 1)
                            if len(args) >= 2:
                                portrait, text = args[:2]
                                sprite = portrait_sprites.get(portrait)
                                DialogBox(gui_handler, _(text), sprite).show()
                        elif command == "play_music":
                            self.music = arg
                            play_music(arg)
                        elif command == "timeline":
                            if self.timeline_name not in watched_timelines:
                                watched_timelines.append(self.timeline_name)
                            self.load_timeline(arg)
                            break
                        elif command == "skip_to":
                            try:
                                arg = float(arg)
                            except ValueError:
                                pass
                            else:
                                self.timeline_skipto(arg)
                                break
                        elif command == "exec":
                            try:
                                six.exec_(arg)
                            except Exception as e:
                                m = _("An error occurred in a timeline 'exec' command:\n\n{}").format(
                                    traceback.format_exc())
                                show_error(m)
                        elif command == "if":
                            try:
                                r = eval(arg)
                            except Exception as e:
                                m = _("An error occurred in a timeline 'if' statement:\n\n{}").format(
                                    traceback.format_exc())
                                show_error(m)
                                r = False
                            finally:
                                if not r:
                                    self.timeline[i] = []
                                    break
                        elif command == "if_watched":
                            if self.timeline_name not in watched_timelines:
                                self.timeline[i] = []
                                break
                        elif command == "if_not_watched":
                            if self.timeline_name in watched_timelines:
                                self.timeline[i] = []
                                break
                        elif command == "while":
                            try:
                                r = eval(arg)
                            except Exception as e:
                                m = _("An error occurred in a timeline 'while' statement:\n\n{}").format(
                                    traceback.format_exc())
                                show_error(m)
                                r = False
                            finally:
                                if r:
                                    cur_timeline = self.timeline[i][:]
                                    while_command = "while {}".format(arg)
                                    self.timeline[i].insert(0, while_command)
                                    t_keys.insert(0, i)
                                    self.timeline[i - 1] = cur_timeline
                                    self.timeline[i] = loop_timeline
                                    i -= 1
                                    self.timeline_step -= 1
                                else:
                                    self.timeline[i] = []
                                    break
                else:
                    del self.timeline[i]
            else:
                break
        else:
            if (self.timeline_name and
                    self.timeline_name not in watched_timelines):
                watched_timelines.append(self.timeline_name)
                self.timeline_name = ""

        self.timeline_step += delta_mult

        if self.death_time is not None:
            a = int(255 * (DEATH_FADE_TIME - self.death_time) / DEATH_FADE_TIME)
            sge.game.project_rectangle(
                0, 0, sge.game.width, sge.game.height, z=100,
                fill=sge.gfx.Color((0, 0, 0, min(a, 255))))

            time_bonus = level_timers.setdefault(main_area, 0)
            if time_bonus < 0 and cleared_levels:
                amt = int(math.copysign(
                    min(math.ceil(abs(self.death_time_bonus) * 3 * time_passed /
                                  DEATH_FADE_TIME),
                        abs(time_bonus)),
                    time_bonus))
                if amt:
                    score += amt
                    level_timers[main_area] -= amt
                    play_sound(coin_sound)

            if self.death_time < 0:
                self.death_time = None
                self.alarms["death"] = DEATH_RESTART_WAIT
            else:
                self.death_time -= time_passed
        elif "death" in self.alarms:
            sge.game.project_rectangle(0, 0, sge.game.width, sge.game.height,
                                       z=100, fill=sge.gfx.Color("black"))

        if self.won:
            if self.win_count_points:
                if self.points:
                    amt = int(math.copysign(
                        min(delta_mult * WIN_COUNT_POINTS_MULT,
                            abs(self.points)),
                        self.points))
                    score += amt
                    self.points -= amt
                    play_sound(coin_sound)
                else:
                    self.win_count_points = False
                    self.alarms["win_count_time"] = WIN_COUNT_CONTINUE_TIME
            elif self.win_count_time:
                time_bonus = level_timers.setdefault(main_area, 0)
                if time_bonus:
                    amt = int(math.copysign(
                        min(delta_mult * WIN_COUNT_TIME_MULT,
                            abs(time_bonus)),
                        time_bonus))
                    score += amt
                    level_timers[main_area] -= amt
                    play_sound(coin_sound)
                else:
                    self.win_count_time = False
                    if main_area not in cleared_levels:
                        self.alarms["win_count_hp"] = WIN_COUNT_CONTINUE_TIME
                    else:
                        self.alarms["win"] = WIN_FINISH_DELAY
            elif (not level_win_music.playing and
                  "win_count_points" not in self.alarms and
                  "win_count_time" not in self.alarms and
                  "win_count_hp" not in self.alarms and
                  "win" not in self.alarms):
                if main_area not in cleared_levels:
                    cleared_levels.append(main_area)

                current_areas = {}
                level_cleared = True

                if self.game_won:
                    self.win_game()
                elif current_worldmap:
                    self.return_to_map(True)
                else:
                    main_area = None
                    current_level += 1
                    if current_level < len(levels):
                        save_game()
                        level = self.__class__.load(levels[current_level],
                                                    True)
                        level.start(transition="fade")
                    else:
                        self.win_game()

    def event_paused_step(self, time_passed, delta_mult):
        # Handle lighting
        if self.ambient_light:
            range_ = max(ACTIVATE_RANGE, LIGHT_RANGE)
        else:
            range_ = ACTIVATE_RANGE

        for view in self.views:
            for obj in self.get_objects_at(
                    view.x - range_, view.y - range_, view.width + range_ * 2,
                    view.height + range_ * 2):
                if isinstance(obj, InteractiveObject):
                    if not self.disable_lights:
                        obj.project_light()

        self.show_hud()

    def event_alarm(self, alarm_id):
        global level_timers
        global score

        if alarm_id == "timer":
            if main_area in levels:
                level_timers.setdefault(main_area, 0)
                if main_area not in cleared_levels:
                    level_timers[main_area] -= SECOND_POINTS
                self.alarms["timer"] = TIMER_FRAMES
        elif alarm_id == "shake_down":
            self.shake_queue -= 1
            for view in self.views:
                view.yport += SHAKE_AMOUNT
            self.alarms["shake_up"] = SHAKE_FRAME_TIME
        elif alarm_id == "shake_up":
            for view in self.views:
                view.yport -= SHAKE_AMOUNT
            if self.shake_queue:
                self.alarms["shake_down"] = SHAKE_FRAME_TIME
        elif alarm_id == "death":
            # Project a black rectangle to prevent showing the level on
            # the last frame.
            sge.game.project_rectangle(0, 0, sge.game.width, sge.game.height,
                                       z=100, fill=sge.gfx.Color("black"))

            if (not cleared_levels and
                    current_checkpoints.get(main_area) is None):
                level_timers[main_area] = level_time_bonus

            if current_worldmap:
                self.return_to_map()
            elif main_area is not None:
                save_game()
                r = self.__class__.load(main_area, True)
                checkpoint = current_checkpoints.get(self.fname)
                if checkpoint is not None:
                    area_name, area_spawn = checkpoint.split(':', 1)
                    r = self.__class__.load(area_name, True)
                    r.spawn = area_spawn
                r.start()
        elif alarm_id == "win_count_points":
            if self.points > 0:
                self.win_count_points = True
            else:
                self.win_count_time = True
        elif alarm_id == "win_count_time":
            self.win_count_time = True
        elif alarm_id == "win_count_hp":
            if GOD:
                self.alarms["win"] = WIN_FINISH_DELAY
            else:
                for obj in self.objects:
                    if isinstance(obj, Player) and obj.hp > 0:
                        obj.hp -= 1
                        score += HP_POINTS
                        play_sound(heal_sound)
                        self.alarms["win_count_hp"] = WIN_COUNT_CONTINUE_TIME
                        break
                else:
                    self.alarms["win"] = WIN_FINISH_DELAY

    @classmethod
    def load(cls, fname, show_prompt=False):
        global level_names
        global tuxdolls_available

        if fname in current_areas:
            r = current_areas[fname]
        elif fname in loaded_levels:
            r = loaded_levels.pop(fname)
        else:
            if show_prompt:
                text = "Loading level..."
                if isinstance(sge.game.current_room, Worldmap):
                    sge.game.refresh()
                    sge.game.current_room.level_text = text
                    sge.game.current_room.event_step(0, 0)
                    sge.game.refresh()
                elif sge.game.current_room is not None:
                    x = sge.game.width / 2
                    y = sge.game.height / 2
                    w = font.get_width(text) + 32
                    h = font.get_height(text) + 32
                    sge.game.project_rectangle(x - w / 2, y - h / 2, w, h,
                                               fill=sge.gfx.Color("black"))
                    sge.game.project_text(font, text, x, y,
                                          color=sge.gfx.Color("white"),
                                          halign="center", valign="middle")
                    sge.game.refresh()
                else:
                    print(_("Loading \"{}\"...").format(fname))

            try:
                r = xsge_tmx.load(os.path.join(DATA, "levels", fname), cls=cls,
                                  types=TYPES)
            except Exception as e:
                m = _("An error occurred when trying to load the level:\n\n{}").format(
                    traceback.format_exc())
                show_error(m)
                r = None
            else:
                r.fname = fname

        if r is not None:
            if r.persistent:
                current_areas[fname] = r

            if fname not in level_names:
                name = r.name
                if name:
                    level_names[fname] = name
                elif fname in levels:
                    level_names[fname] = "Level {}".format(
                        levels.index(fname) + 1)
                else:
                    level_names[fname] = "???"

            if main_area in levels and main_area not in tuxdolls_available:
                for obj in r.objects:
                    if (isinstance(obj, TuxDoll) or
                            (isinstance(obj, (ItemBlock, HiddenItemBlock)) and
                             obj.item == "tuxdoll")):
                        tuxdolls_available.append(main_area)
                        break
            elif fname in levels and fname not in tuxdolls_available:
                for obj in r.objects:
                    if (isinstance(obj, TuxDoll) or
                            (isinstance(obj, (ItemBlock, HiddenItemBlock)) and
                             obj.item == "tuxdoll")):
                        tuxdolls_available.append(fname)
                        break

        return r


class LevelTester(Level):

    def return_to_map(self):
        sge.game.end()

    def win_game(self):
        sge.game.end()

    def event_alarm(self, alarm_id):
        if alarm_id == "death":
            sge.game.end()
        else:
            super(LevelTester, self).event_alarm(alarm_id)


class LevelRecorder(LevelTester):

    def __init__(self, *args, **kwargs):
        super(LevelRecorder, self).__init__(*args, **kwargs)
        self.recording = {}

    def add_recording_event(self, command):
        self.recording.setdefault(self.timeline_step, []).append(command)

    def event_key_press(self, key, char):
        if key == "f12":
            jt = self.recording

            import time
            fname = "recording_{}.json".format(time.time())
            with open(fname, 'w') as f:
                json.dump(jt, f, indent=4, sort_keys=True)

            sge.game.end()

        for i in self.timeline_objects:
            obj = self.timeline_objects[i]()
            if isinstance(obj, Player) and obj.human:
                if key in left_key[obj.player]:
                    self.add_recording_event(
                        "setattr {} left_pressed 1".format(obj.ID))
                if key in right_key[obj.player]:
                    self.add_recording_event(
                        "setattr {} right_pressed 1".format(obj.ID))
                if key in up_key[obj.player]:
                    self.add_recording_event("call {} press_up".format(obj.ID))
                    self.add_recording_event(
                        "setattr {} up_pressed 1".format(obj.ID))
                if key in down_key[obj.player]:
                    self.add_recording_event(
                        "setattr {} down_pressed 1".format(obj.ID))
                if key in jump_key[obj.player]:
                    self.add_recording_event("call {} jump".format(obj.ID))
                    self.add_recording_event(
                        "setattr {} jump_pressed 1".format(obj.ID))
                if key in action_key[obj.player]:
                    self.add_recording_event("call {} action".format(obj.ID))
                    self.add_recording_event(
                        "setattr {} action_pressed 1".format(obj.ID))
                if key in sneak_key[obj.player]:
                    self.add_recording_event(
                        "setattr {} sneak_pressed 1".format(obj.ID))

    def event_key_release(self, key):
        for i in self.timeline_objects:
            obj = self.timeline_objects[i]()
            if isinstance(obj, Player) and obj.human:
                if key in left_key[obj.player]:
                    self.add_recording_event(
                        "setattr {} left_pressed 0".format(obj.ID))
                if key in right_key[obj.player]:
                    self.add_recording_event(
                        "setattr {} right_pressed 0".format(obj.ID))
                if key in up_key[obj.player]:
                    self.add_recording_event(
                        "setattr {} up_pressed 0".format(obj.ID))
                if key in down_key[obj.player]:
                    self.add_recording_event(
                        "setattr {} down_pressed 0".format(obj.ID))
                if key in jump_key[obj.player]:
                    self.add_recording_event(
                        "call {} jump_release".format(obj.ID))
                    self.add_recording_event(
                        "setattr {} jump_pressed 0".format(obj.ID))
                if key in action_key[obj.player]:
                    self.add_recording_event(
                        "setattr {} action_pressed 0".format(obj.ID))
                if key in sneak_key[obj.player]:
                    self.add_recording_event(
                        "setattr {} sneak_pressed 0".format(obj.ID))


class SpecialScreen(Level):

    pass


class TitleScreen(SpecialScreen):

    def show_hud(self):
        pass

    def event_room_resume(self):
        super(TitleScreen, self).event_room_resume()
        MainMenu.create()

    def event_key_press(self, key, char):
        pass


class CreditsScreen(SpecialScreen):

    def event_room_start(self):
        super(CreditsScreen, self).event_room_start()

        if self.fname in current_areas:
            del current_areas[self.fname]

        if self.fname in loaded_levels:
            del loaded_levels[self.fname]

        with open(os.path.join(DATA, "credits.json"), 'r') as f:
            sections = json.load(f)

        logo_section = sge.dsp.Object.create(self.width / 2, self.height,
                                             sprite=logo_sprite,
                                             tangible=False)
        self.sections = [logo_section]
        for section in sections:
            if "title" in section:
                head_sprite = sge.gfx.Sprite.from_text(
                    font_big, section["title"], width=self.width,
                    color=sge.gfx.Color("white"), halign="center")
                x = self.width / 2
                y = self.sections[-1].bbox_bottom + font_big.size * 3
                head_section = sge.dsp.Object.create(x, y, sprite=head_sprite,
                                                     tangible=False)
                self.sections.append(head_section)

            if "lines" in section:
                for line in section["lines"]:
                    list_sprite = sge.gfx.Sprite.from_text(
                        font, line, width=self.width - 2 * TILE_SIZE,
                        color=sge.gfx.Color("white"), halign="center")
                    x = self.width / 2
                    y = self.sections[-1].bbox_bottom + font.size
                    list_section = sge.dsp.Object.create(
                        x, y, sprite=list_sprite, tangible=False)
                    self.sections.append(list_section)

        for obj in self.sections:
            obj.yvelocity = -0.5

    def event_step(self, time_passed, delta_mult):
        if self.sections[0].yvelocity > 0 and self.sections[0].y > self.height:
            for obj in self.sections:
                obj.yvelocity = 0

        if self.sections[-1].bbox_bottom < 0 and "end" not in self.alarms:
            sge.snd.Music.stop(fade_time=3000)
            self.alarms["end"] = 3.5 * FPS

    def event_alarm(self, alarm_id):
        if alarm_id == "end":
            sge.game.start_room.start()

    def event_key_press(self, key, char):
        if key in itertools.chain.from_iterable(down_key):
            if "end" not in self.alarms:
                for obj in self.sections:
                    obj.yvelocity -= 0.25
        elif key in itertools.chain.from_iterable(up_key):
            if "end" not in self.alarms:
                for obj in self.sections:
                    obj.yvelocity += 0.25
        elif (key in itertools.chain.from_iterable(jump_key) or
                key in itertools.chain.from_iterable(action_key) or
                key in itertools.chain.from_iterable(pause_key)):
            sge.game.start_room.start()

    def event_joystick(self, js_name, js_id, input_type, input_id, value):
        js = (js_id, input_type, input_id)
        if value >= joystick_threshold:
            if js in itertools.chain.from_iterable(down_js):
                if "end" not in self.alarms:
                    for obj in self.sections:
                        obj.yvelocity -= 0.25
            elif js in itertools.chain.from_iterable(up_js):
                if "end" not in self.alarms:
                    for obj in self.sections:
                        obj.yvelocity += 0.25
            elif (js in itertools.chain.from_iterable(jump_js) or
                    js in itertools.chain.from_iterable(action_js) or
                    js in itertools.chain.from_iterable(pause_js)):
                sge.game.start_room.start()


class Worldmap(sge.dsp.Room):

    """Handles worldmaps."""

    def __init__(self, objects=(), width=None, height=None, views=None,
                 background=None, background_x=0, background_y=0,
                 object_area_width=TILE_SIZE * 2,
                 object_area_height=TILE_SIZE * 2, music=None):
        self.music = music
        super(Worldmap, self).__init__(objects, width, height, views,
                                       background, background_x, background_y,
                                       object_area_width, object_area_height)

    def show_menu(self):
        sge.snd.Music.pause()
        play_sound(pause_sound)
        WorldmapMenu.create()

    def event_room_start(self):
        self.level_text = None
        self.level_tuxdoll_available = False
        self.level_tuxdoll_found = False
        self.event_room_resume()

    def event_room_resume(self):
        global loaded_levels
        global main_area
        global current_areas
        global level_cleared

        main_area = None

        for obj in self.objects:
            if isinstance(obj, MapSpace):
                obj.update_sprite()

        play_music(self.music)
        level_cleared = False

    def event_step(self, time_passed, delta_mult):
        text = " {}/{}".format(len(tuxdolls_found), len(tuxdolls_available))
        w = tuxdoll_sprite.width + font.get_width(text)

        x = sge.game.width / 2 + tuxdoll_sprite.origin_x - w / 2
        y = tuxdoll_sprite.origin_y + 16
        sge.game.project_sprite(tuxdoll_shadow_sprite, 0, x + 2, y + 2)
        sge.game.project_sprite(tuxdoll_sprite, 0, x, y)

        x += tuxdoll_sprite.width - tuxdoll_sprite.origin_x
        sge.game.project_text(font, text, x + 2, y + 2,
                              color=sge.gfx.Color("black"), halign="left",
                              valign="middle")
        sge.game.project_text(font, text, x, y, color=sge.gfx.Color("white"),
                              halign="left", valign="middle")

        if self.level_text:
            x = sge.game.width / 2
            y = sge.game.height - font.size
            sge.game.project_text(font, self.level_text, x + 2, y + 2,
                                  color=sge.gfx.Color("black"),
                                  halign="center", valign="bottom")
            sge.game.project_text(font, self.level_text, x, y,
                                  color=sge.gfx.Color("white"),
                                  halign="center", valign="bottom")

        if self.level_tuxdoll_available:
            x = sge.game.width / 2
            y = sge.game.height - font.size * 4
            if self.level_tuxdoll_found:
                sge.game.project_sprite(tuxdoll_shadow_sprite, 0, x + 2, y + 2)
                sge.game.project_sprite(tuxdoll_sprite, 0, x, y)
            else:
                sge.game.project_sprite(tuxdoll_transparent_sprite, 0, x, y)

    @classmethod
    def load(cls, fname):
        if fname in loaded_worldmaps:
            return loaded_worldmaps.pop(fname)
        else:
            return xsge_tmx.load(os.path.join(DATA, "worldmaps", fname),
                                 cls=cls, types=TYPES)


class SolidLeft(xsge_physics.SolidLeft):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("visible", False)
        kwargs.setdefault("checks_collisions", False)
        super(SolidLeft, self).__init__(*args, **kwargs)


class SolidRight(xsge_physics.SolidRight):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("visible", False)
        kwargs.setdefault("checks_collisions", False)
        super(SolidRight, self).__init__(*args, **kwargs)


class SolidTop(xsge_physics.SolidTop):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("visible", False)
        kwargs.setdefault("checks_collisions", False)
        super(SolidTop, self).__init__(*args, **kwargs)


class SolidBottom(xsge_physics.SolidBottom):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("visible", False)
        kwargs.setdefault("checks_collisions", False)
        super(SolidBottom, self).__init__(*args, **kwargs)


class Solid(xsge_physics.Solid):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("visible", False)
        kwargs.setdefault("checks_collisions", False)
        super(Solid, self).__init__(*args, **kwargs)


class SlopeTopLeft(xsge_physics.SlopeTopLeft):

    xsticky_top = True

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("visible", False)
        kwargs.setdefault("checks_collisions", False)
        super(SlopeTopLeft, self).__init__(*args, **kwargs)


class SlopeTopRight(xsge_physics.SlopeTopRight):

    xsticky_top = True

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("visible", False)
        kwargs.setdefault("checks_collisions", False)
        super(SlopeTopRight, self).__init__(*args, **kwargs)


class SlopeBottomLeft(xsge_physics.SlopeBottomLeft):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("visible", False)
        kwargs.setdefault("checks_collisions", False)
        super(SlopeBottomLeft, self).__init__(*args, **kwargs)


class SlopeBottomRight(xsge_physics.SlopeBottomRight):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("visible", False)
        kwargs.setdefault("checks_collisions", False)
        super(SlopeBottomRight, self).__init__(*args, **kwargs)


class MovingPlatform(xsge_physics.SolidTop, xsge_physics.MobileWall):

    sticky_top = True

    def __init__(self, x, y, z=0, **kwargs):
        kwargs.setdefault("sprite", platform_sprite)
        super(MovingPlatform, self).__init__(x, y, z, **kwargs)
        self.path = None
        self.following = False

    def event_step(self, time_passed, delta_mult):
        super(MovingPlatform, self).event_step(time_passed, delta_mult)

        if self.path and not self.following:
            for other in self.collision(Player, y=(self.y - 1)):
                if self in other.get_bottom_touching_wall():
                    self.path.follow_start(self, self.path.path_speed,
                                           accel=self.path.path_accel,
                                           decel=self.path.path_decel,
                                           loop=self.path.path_loop)
                    break


class HurtLeft(SolidLeft):

    pass


class HurtRight(SolidRight):

    pass


class HurtTop(SolidTop):

    pass


class HurtBottom(SolidBottom):

    pass


class SpikeLeft(HurtLeft, xsge_physics.Solid):

    pass


class SpikeRight(HurtRight, xsge_physics.Solid):

    pass


class SpikeTop(HurtTop, xsge_physics.Solid):

    pass


class SpikeBottom(HurtBottom, xsge_physics.Solid):

    pass


class Death(sge.dsp.Object):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("visible", False)
        kwargs.setdefault("checks_collisions", False)
        super(Death, self).__init__(*args, **kwargs)


class LevelEnd(sge.dsp.Object):

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("visible", False)
        kwargs.setdefault("checks_collisions", False)
        super(LevelEnd, self).__init__(*args, **kwargs)


class Player(xsge_physics.Collider):

    name = "Ian C."
    max_hp = PLAYER_MAX_HP
    max_speed = PLAYER_MAX_SPEED
    acceleration = PLAYER_ACCELERATION
    air_acceleration = PLAYER_AIR_ACCELERATION
    friction = PLAYER_FRICTION
    air_friction = PLAYER_AIR_FRICTION
    jump_height = PLAYER_JUMP_HEIGHT
    gravity = GRAVITY
    fall_speed = PLAYER_FALL_SPEED
    slide_speed = PLAYER_SLIDE_SPEED
    hitstun_time = PLAYER_HITSTUN
    hitstun_speed = PLAYER_HITSTUN_SPEED

    def __init__(self, x, y, z=0, sprite=None, visible=True, active=True,
                 checks_collisions=True, tangible=True, bbox_x=-13, bbox_y=2,
                 bbox_width=26, bbox_height=30, regulate_origin=True,
                 collision_ellipse=False, collision_precise=False, xvelocity=0,
                 yvelocity=0, xacceleration=0, yacceleration=0,
                 xdeceleration=0, ydeceleration=0, image_index=0,
                 image_origin_x=None, image_origin_y=None, image_fps=None,
                 image_xscale=1, image_yscale=1, image_rotation=0,
                 image_alpha=255, image_blend=None, ID="player", player=0,
                 human=True, lose_on_death=True, view_frozen=False):
        self.ID = ID
        self.player = player
        self.human = human
        self.lose_on_death = lose_on_death
        self.view_frozen = view_frozen

        self.left_pressed = False
        self.right_pressed = False
        self.up_pressed = False
        self.down_pressed = False
        self.halt_pressed = False
        self.jump_pressed = False
        self.shoot_pressed = False
        self.aim_up_pressed = False
        self.aim_down_pressed = False
        self.hp = self.max_hp
        self.hitstun = False
        self.facing = 1
        self.view = None

        if GOD:
            image_blend = sge.gfx.Color("yellow")

        super(Player, self).__init__(
            x, y, z=z, sprite=sprite, visible=visible, active=active,
            checks_collisions=checks_collisions, tangible=tangible,
            bbox_x=bbox_x, bbox_y=bbox_y, bbox_width=bbox_width,
            bbox_height=bbox_height, regulate_origin=regulate_origin,
            collision_ellipse=collision_ellipse,
            collision_precise=collision_precise, xvelocity=xvelocity,
            yvelocity=yvelocity, xacceleration=xacceleration,
            yacceleration=yacceleration, xdeceleration=xdeceleration,
            ydeceleration=ydeceleration, image_index=image_index,
            image_origin_x=image_origin_x, image_origin_y=image_origin_y,
            image_fps=image_fps, image_xscale=image_xscale,
            image_yscale=image_yscale, image_rotation=image_rotation,
            image_alpha=image_alpha, image_blend=image_blend)

    def refresh_input(self):
        if self.human:
            key_controls = [left_key, right_key, up_key, down_key, halt_key,
                            jump_key, shoot_key, aim_up_key, aim_down_key]
            js_controls = [left_js, right_js, up_js, down_js, halt_js, jump_js,
                           shoot_js, aim_up_js, aim_down_js]
            states = [0 for i in key_controls]

            for i in six.moves.range(len(key_controls)):
                for choice in key_controls[i][self.player]:
                    value = sge.keyboard.get_pressed(choice)
                    states[i] = max(states[i], value)

            for i in six.moves.range(len(js_controls)):
                for choice in js_controls[i][self.player]:
                    j, t, c = choice
                    value = min(sge.joystick.get_value(j, t, c), 1)
                    if value >= joystick_threshold:
                        states[i] = max(states[i], value)

            self.left_pressed = states[0]
            self.right_pressed = states[1]
            self.up_pressed = states[2]
            self.down_pressed = states[3]
            self.halt_pressed = states[4]
            self.jump_pressed = states[5]
            self.shoot_pressed = states[6]
            self.aim_up_pressed = states[7]
            self.aim_down_pressed = states[8]

    def jump(self):
        if self.on_floor or self.was_on_floor:
            if abs(self.xvelocity) >= self.run_speed:
                self.yvelocity = get_jump_speed(self.run_jump_height,
                                                self.gravity)
            else:
                self.yvelocity = get_jump_speed(self.jump_height, self.gravity)
            self.on_floor = []
            self.was_on_floor = []
            play_sound(jump_sound, self.x, self.y)

    def jump_release(self):
        if self.yvelocity < 0:
            self.yvelocity /= 2

    def shoot(self):
        pass

    def hurt(self, damage=1):
        if not self.hitstun:
            if not GOD:
                self.hp -= damage

            if self.hp <= 0:
                self.kill()
            else:
                play_sound(hurt_sound, self.x, self.y)
                self.hitstun = True
                self.image_alpha = 128
                self.alarms["hitstun"] = self.hitstun_time

    def kill(self):
        play_sound(kill_sound, self.x, self.y)

        if self.lose_on_death:
            sge.game.current_room.die()

        self.destroy()

    def show_hud(self):
        if not NO_HUD:
            # TODO: Show HUD

            if not self.human:
                room = sge.game.current_room
                if (room.timeline_skip_target is not None and
                        room.timeline_step < room.timeline_skip_target):
                    room.status_text = _("Press the Menu button to skip...")
                else:
                    room.status_text = _("Cinematic mode enabled")

    def set_image(self):
        pass

    def event_create(self):
        sge.game.current_room.add_timeline_object(self)

        self.last_x = self.x
        self.last_y = self.y
        self.on_slope = self.get_bottom_touching_slope()
        self.on_floor = self.get_bottom_touching_wall() + self.on_slope
        self.was_on_floor = self.on_floor

        self.view = sge.game.current_room.views[self.player]
        self.view.x = self.x - self.view.width / 2
        self.view.y = self.y - self.view.height + CAMERA_TARGET_MARGIN_BOTTOM

    def event_begin_step(self, time_passed, delta_mult):
        self.refresh_input()

        h_control = bool(self.right_pressed) - bool(self.left_pressed)
        current_h_movement = (self.xvelocity > 0) - (self.xvelocity < 0)

        self.xacceleration = 0
        self.yacceleration = 0
        self.xdeceleration = 0

        if abs(self.xvelocity) >= self.max_speed:
            self.xvelocity = self.max_speed * current_h_movement

        if h_control:
            self.facing = h_control
            self.image_xscale = h_control * abs(self.image_xscale)

            if self.halt_pressed:
                target_speed = 0
            else:
                h_factor = abs(self.right_pressed - self.left_pressed)
                target_speed = min(h_factor * self.max_speed, self.max_speed)

            if (abs(self.xvelocity) < target_speed or
                    h_control != current_h_movement):
                if self.on_floor or self.was_on_floor:
                    self.xacceleration = self.acceleration * h_control
                else:
                    self.xacceleration = self.air_acceleration * h_control
            else:
                if self.on_floor or self.was_on_floor:
                    dc = self.friction
                else:
                    dc = self.air_friction

                if abs(self.xvelocity) - dc * delta_mult > target_speed:
                    self.xdeceleration = dc
                else:
                    self.xvelocity = target_speed * current_h_movement

        if current_h_movement and h_control != current_h_movement:
            if self.on_floor or self.was_on_floor:
                self.xdeceleration = self.friction
            else:
                self.xdeceleration = self.air_friction

        if not self.on_floor and not self.was_on_floor:
            if self.yvelocity < self.fall_speed:
                self.yacceleration = self.gravity
            else:
                self.yvelocity = self.fall_speed
        elif self.on_slope:
            self.yvelocity = (self.slide_speed *
                              (self.on_slope[0].bbox_height /
                               self.on_slope[0].bbox_width))

    def event_step(self, time_passed, delta_mult):
        on_floor = self.get_bottom_touching_wall()
        self.on_slope = self.get_bottom_touching_slope() if not on_floor else []
        self.was_on_floor = self.on_floor
        self.on_floor = on_floor + self.on_slope
        h_control = bool(self.right_pressed) - bool(self.left_pressed)
        v_control = bool(self.down_pressed) - bool(self.up_pressed)

        for block in self.on_floor:
            if block in self.was_on_floor and isinstance(block, HurtTop):
                self.hurt()

        # Set image
        if "fixed_sprite" not in self.alarms:
            self.set_image()

        # Move view
        if not self.view_frozen:
            view_target_x = (self.x - self.view.width / 2 +
                             self.xvelocity * CAMERA_OFFSET_FACTOR)
            if abs(view_target_x - self.view.x) > 0.5:
                self.view.x += ((view_target_x - self.view.x) *
                                CAMERA_HSPEED_FACTOR)
            else:
                self.view.x = view_target_x

            view_min_y = self.y - self.view.height + CAMERA_MARGIN_BOTTOM
            view_max_y = self.y - CAMERA_MARGIN_TOP

            if self.on_floor and self.was_on_floor:
                view_target_y = (self.y - self.view.height +
                                 CAMERA_TARGET_MARGIN_BOTTOM)
                if abs(view_target_y - self.view.y) > 0.5:
                    self.view.y += ((view_target_y - self.view.y) *
                                    CAMERA_VSPEED_FACTOR)
                else:
                    self.view.y = view_target_y

            if self.view.y < view_min_y:
                self.view.y = view_min_y
            elif self.view.y > view_max_y:
                self.view.y = view_max_y

        self.last_x = self.x
        self.last_y = self.y

        self.show_hud()

    def event_paused_step(self, time_passed, delta_mult):
        self.show_hud()

    def event_alarm(self, alarm_id):
        if alarm_id == "hitstun":
            self.hitstun = False
            self.image_alpha = 255

    def event_key_press(self, key, char):
        if self.human:
            if key in jump_key[self.player]:
                self.jump()
            if key in shoot_key[self.player]:
                self.shoot()

        if not isinstance(sge.game.current_room, SpecialScreen):
            if key == "escape" or key in pause_key[self.player]:
                sge.game.current_room.pause()

    def event_key_release(self, key):
        if self.human:
            if key in jump_key[self.player]:
                self.jump_release()

    def event_joystick(self, js_name, js_id, input_type, input_id, value):
        if self.human:
            js = (js_id, input_type, input_id)
            if value >= joystick_threshold:
                if js in jump_js[self.player]:
                    self.jump()
                if js in shoot_js[self.player]:
                    self.shoot()
                if js in pause_js[self.player]:
                    sge.game.current_room.pause()
            else:
                if js in jump_js[self.player]:
                    self.jump_release()

    def event_collision(self, other, xdirection, ydirection):
        if isinstance(other, InteractiveObject):
            other.touch(self)

    def event_physics_collision_left(self, other, move_loss):
        for block in self.get_left_touching_wall():
            if isinstance(block, HurtRight):
                self.hurt()

        if isinstance(other, xsge_physics.SolidRight):
            self.xvelocity = max(self.xvelocity, 0)

    def event_physics_collision_right(self, other, move_loss):
        for block in self.get_right_touching_wall():
            if isinstance(block, HurtLeft):
                self.hurt()

        if isinstance(other, xsge_physics.SolidLeft):
            self.xvelocity = min(self.xvelocity, 0)

    def event_physics_collision_top(self, other, move_loss):
        top_touching = self.get_top_touching_wall()

        tmv = 0
        for i in six.moves.range(CEILING_LAX):
            if (not self.get_left_touching_wall() and
                    not self.get_left_touching_slope()):
                self.x -= 1
                tmv -= 1
                if (not self.get_top_touching_wall() and
                        not self.get_top_touching_slope()):
                    self.move_y(-move_loss)
                    break
        else:
            self.x -= tmv
            tmv = 0
            for i in six.moves.range(CEILING_LAX):
                if (not self.get_left_touching_wall() and
                        not self.get_left_touching_slope()):
                    self.x += 1
                    tmv += 1
                    if (not self.get_top_touching_wall() and
                            not self.get_top_touching_slope()):
                        self.move_y(-move_loss)
                        break
            else:
                self.x -= tmv
                tmv = 0
                self.yvelocity = max(self.yvelocity, 0)

        for block in top_touching:
            if isinstance(block, HurtBottom):
                self.hurt()

    def event_physics_collision_bottom(self, other, move_loss):
        for block in self.get_bottom_touching_wall():
            if isinstance(block, HurtTop):
                self.hurt()

        if isinstance(other, xsge_physics.SolidTop):
            self.yvelocity = min(self.yvelocity, 0)
        elif isinstance(other, (xsge_physics.SlopeTopLeft,
                                xsge_physics.SlopeTopRight)):
            self.yvelocity = min(self.slide_speed * (other.bbox_height /
                                                     other.bbox_width),
                                 self.yvelocity)


class Anneroy(Player):

    name = "Anneroy"

    torso = None

    def set_image(self):
        h_control = bool(self.right_pressed) - bool(self.left_pressed)

        if self.on_floor and self.was_on_floor:
            xm = (self.xvelocity > 0) - (self.xvelocity < 0)
            speed = abs(self.xvelocity)
            if speed > 0:
                # TODO: Set running animation

                self.image_speed = speed * PLAYER_RUN_FRAMES_PER_PIXEL
                if xm != self.facing:
                    self.image_speed *= -1
            else:
                # TODO: Set standing animation
                pass
        else:
            if self.yvelocity < 0:
                # TODO: Set jumping up animation
                pass
            else:
                # TODO: Set falling animation
                pass

        # TODO: Set torso animation

    def event_create(self):
        super(Anneroy, self).event_create()
        self.torso = sge.dsp.Object.create(self.x, self.y, self.z + 0.1)

    def event_update_position(self, delta_mult):
        super(Anneroy, self).event_update_position(delta_mult)

        if self.torso is not None:
            # TODO: Adjust x and y
            self.torso.x = self.x
            self.torso.y = self.y
            self.torso.image_xscale = math.copysign(self.torso.image_xscale,
                                                    self.image_xscale)
            self.torso.image_yscale = math.copysign(self.torso.image_yscale,
                                                    self.image_yscale)


class DeadMan(sge.dsp.Object):

    """Object which falls off the screen, then gets destroyed."""

    gravity = GRAVITY
    fall_speed = PLAYER_DIE_FALL_SPEED

    def event_begin_step(self, time_passed, delta_mult):
        if self.yvelocity < self.fall_speed:
            self.yacceleration = self.gravity
        else:
            self.yvelocity = self.fall_speed
            self.yacceleration = 0

    def event_step(self, time_passed, delta_mult):
        if self.y - self.image_origin_y > sge.game.current_room.height:
            self.destroy()


class Corpse(xsge_physics.Collider):

    """Like DeadMan, but just falls to the floor, not off-screen."""

    gravity = GRAVITY
    fall_speed = ENEMY_FALL_SPEED

    def event_create(self):
        self.alarms["die"] = 90

    def event_begin_step(self, time_passed, delta_mult):
        if self.get_bottom_touching_wall() or self.get_bottom_touching_slope():
            self.yvelocity = 0
        else:
            if self.yvelocity < self.fall_speed:
                self.yacceleration = self.gravity
            else:
                self.yvelocity = min(self.yvelocity, self.fall_speed)
                self.yacceleration = 0

    def event_alarm(self, alarm_id):
        if alarm_id == "die":
            self.destroy()


class Smoke(sge.dsp.Object):

    def event_animation_end(self):
        self.destroy()


class InteractiveObject(sge.dsp.Object):

    killed_by_void = True
    freezable = False

    def get_nearest_player(self):
        player = None
        dist = 0
        for obj in sge.game.current_room.objects:
            if isinstance(obj, Player):
                ndist = math.hypot(self.x - obj.x, self.y - obj.y)
                if player is None or ndist < dist:
                    player = obj
                    dist = ndist
        return player

    def set_direction(self, direction):
        self.image_xscale = abs(self.image_xscale) * direction

    def move(self):
        pass

    def touch(self, other):
        pass

    def freeze(self):
        pass

    def project_light(self):
        pass

    def event_begin_step(self, time_passed, delta_mult):
        self.move()


class InteractiveCollider(InteractiveObject, xsge_physics.Collider):

    def stop_left(self):
        self.xvelocity = 0

    def stop_right(self):
        self.xvelocity = 0

    def stop_up(self):
        self.yvelocity = 0

    def stop_down(self):
        self.yvelocity = 0

    def touch_hurt(self):
        pass

    def event_physics_collision_left(self, other, move_loss):
        if isinstance(other, HurtRight):
            self.touch_hurt()

        if isinstance(other, xsge_physics.SolidRight):
            self.stop_left()
        elif isinstance(other, xsge_physics.SlopeTopRight):
            if self.yvelocity > 0:
                self.stop_down()
        elif isinstance(other, xsge_physics.SlopeBottomRight):
            if self.yvelocity < 0:
                self.stop_up()

    def event_physics_collision_right(self, other, move_loss):
        if isinstance(other, HurtLeft):
            self.touch_hurt()

        if isinstance(other, xsge_physics.SolidLeft):
            self.stop_right()
        elif isinstance(other, xsge_physics.SlopeTopLeft):
            if self.yvelocity > 0:
                self.stop_down()
        elif isinstance(other, xsge_physics.SlopeBottomLeft):
            if self.yvelocity < 0:
                self.stop_up()

    def event_physics_collision_top(self, other, move_loss):
        if isinstance(other, HurtBottom):
            self.touch_hurt()
        if isinstance(other, (xsge_physics.SolidBottom,
                              xsge_physics.SlopeBottomLeft,
                              xsge_physics.SlopeBottomRight)):
            self.stop_up()

    def event_physics_collision_bottom(self, other, move_loss):
        if isinstance(other, HurtTop):
            self.touch_hurt()
        if isinstance(other, (xsge_physics.SolidTop, xsge_physics.SlopeTopLeft,
                              xsge_physics.SlopeTopRight)):
            self.stop_down()


class FallingObject(InteractiveCollider):

    """
    Falls based on gravity. If on a slope, falls at a constant speed
    based on the steepness of the slope.
    """

    gravity = GRAVITY
    fall_speed = ENEMY_FALL_SPEED
    slide_speed = ENEMY_SLIDE_SPEED

    was_on_floor = False

    def move(self):
        on_floor = self.get_bottom_touching_wall()
        on_slope = self.get_bottom_touching_slope()
        if self.was_on_floor and (on_floor or on_slope) and self.yvelocity >= 0:
            self.yacceleration = 0
            if on_floor:
                if self.yvelocity > 0:
                    self.yvelocity = 0
                    self.stop_down()
            elif on_slope:
                self.yvelocity = self.slide_speed * (on_slope[0].bbox_height /
                                                     on_slope[0].bbox_width)
        else:
            if self.yvelocity < self.fall_speed:
                self.yacceleration = self.gravity
            else:
                self.yvelocity = self.fall_speed
                self.yacceleration = 0

        self.was_on_floor = on_floor or on_slope


class WalkingObject(FallingObject):

    """
    Walks toward the player.  Turns around at walls, and can also be set
    to turn around at ledges with the stayonplatform attribute.
    """

    walk_speed = ENEMY_WALK_SPEED
    stayonplatform = False

    def deactivate(self):
        super(WalkingObject, self).deactivate()
        self.xvelocity = 0

    def set_direction(self, direction):
        self.xvelocity = self.walk_speed * direction
        self.image_xscale = abs(self.image_xscale) * direction

    def move(self):
        super(WalkingObject, self).move()

        if not self.xvelocity:
            player = self.get_nearest_player()
            if player is not None:
                self.set_direction(1 if self.x < player.x else -1)
            else:
                self.set_direction(-1)

        on_floor = self.get_bottom_touching_wall()
        on_slope = self.get_bottom_touching_slope()
        if (on_floor or on_slope) and self.stayonplatform:
            if self.xvelocity < 0:
                for tile in on_floor:
                    if tile.bbox_left < self.x:
                        break
                else:
                    if not on_slope:
                        self.set_direction(1)
            else:
                for tile in on_floor:
                    if tile.bbox_right > self.x:
                        break
                else:
                    if not on_slope:
                        self.set_direction(-1)

    def stop_left(self):
        self.set_direction(1)

    def stop_right(self):
        self.set_direction(-1)


class CrowdBlockingObject(InteractiveObject):

    """Blocks CrowdObject instances, causing them to turn around."""

    pass


class CrowdObject(WalkingObject, CrowdBlockingObject):

    """
    Turns around when colliding with a CrowdBlockingObject.  (Note: this
    class is itself derived from CrowdBlockingObject.)
    """

    def event_collision(self, other, xdirection, ydirection):
        if isinstance(other, CrowdBlockingObject):
            if xdirection:
                self.set_direction(-xdirection)
            else:
                if self.x > other.x:
                    self.set_direction(1)
                elif self.x < other.x:
                    self.set_direction(-1)
                elif id(self) > id(other):
                    self.set_direction(1)
                else:
                    self.set_direction(-1)
        else:
            super(CrowdObject, self).event_collision(other, xdirection,
                                                     ydirection)


class FreezableObject(InteractiveObject):

    """Provides basic freeze behavior."""

    freezable = True
    frozen_sprite = None
    frozen_time = THAW_TIME_DEFAULT
    frozen = False

    def permafreeze(self):
        prev_frozen_time = self.frozen_time
        self.frozen_time = None
        self.freeze()
        self.frozen_time = prev_frozen_time

    def freeze(self):
        if self.frozen_sprite is None:
            self.frozen_sprite = sge.gfx.Sprite(
                width=self.sprite.width, height=self.sprite.height,
                origin_x=self.sprite.origin_x, origin_y=self.sprite.origin_y,
                fps=THAW_FPS, bbox_x=self.sprite.bbox_x,
                bbox_y=self.sprite.bbox_y, bbox_width=self.sprite.bbox_width,
                bbox_height=self.sprite.bbox_height)
            self.frozen_sprite.append_frame()
            self.frozen_sprite.draw_sprite(self.sprite, self.image_index,
                                           self.sprite.origin_x,
                                           self.sprite.origin_y)
            colorizer = sge.gfx.Sprite(width=self.frozen_sprite.width,
                                       height=self.frozen_sprite.height)
            colorizer.draw_rectangle(0, 0, colorizer.width, colorizer.height,
                                     fill=sge.gfx.Color((128, 128, 255)))
            self.frozen_sprite.draw_sprite(colorizer, 0, 0, 0, frame=0,
                                           blend_mode=sge.BLEND_RGB_MULTIPLY)

        frozen_self = FrozenObject.create(self.x, self.y, self.z,
                                          sprite=self.frozen_sprite,
                                          image_fps=0,
                                          image_xscale=self.image_xscale,
                                          image_yscale=self.image_yscale)
        frozen_self.unfrozen = self
        self.frozen = True
        self.tangible = False
        self.active = False
        self.visible = False
        if self.frozen_time is not None:
            frozen_self.alarms["thaw_warn"] = self.frozen_time


class FrozenObject(InteractiveObject, xsge_physics.Solid):

    freezable = True
    unfrozen = None

    def thaw(self):
        if self.unfrozen is not None:
            self.unfrozen.frozen = False
            self.unfrozen.tangible = True
            self.unfrozen.visible = True
            self.unfrozen.activate()
        self.destroy()

    def burn(self):
        self.thaw()
        play_sound(sizzle_sound, self.x, self.y)

    def freeze(self):
        if self.unfrozen is not None:
            self.thaw()
            self.unfrozen.freeze()

    def event_alarm(self, alarm_id):
        if self.unfrozen is not None:
            if alarm_id == "thaw_warn":
                self.image_fps = None
                self.alarms["thaw"] = THAW_WARN_TIME
            elif alarm_id == "thaw":
                self.thaw()


class FlyingEnemy(CrowdBlockingObject):

    def move(self):
        if abs(self.xvelocity) > abs(self.yvelocity):
            self.image_xscale = math.copysign(self.image_xscale, self.xvelocity)
            self.had_xv = 5
        elif self.had_xv > 0:
            self.had_xv -= 1
        else:
            player = self.get_nearest_player()
            if player is not None:
                if self.x < player.x:
                    self.image_xscale = abs(self.image_xscale)
                else:
                    self.image_xscale = -abs(self.image_xscale)


class Crusher(FallingObject, xsge_physics.MobileColliderWall,
              xsge_physics.Solid):

    nonstick_left = True
    nonstick_right = True
    nonstick_top = True
    nonstick_bottom = True
    sticky_top = True
    burnable = True
    freezable = True
    gravity = 0
    fall_speed = CRUSHER_FALL_SPEED
    crushing = False

    def touch(self, other):
        other.hurt()

    def touch_death(self):
        pass

    def touch_hurt(self):
        pass

    def stop_up(self):
        self.yvelocity = 0
        self.crushing = False

    def stop_down(self):
        play_sound(brick_sound, self.x, self.y)
        self.yvelocity = 0
        self.gravity = 0
        sge.game.current_room.shake(CRUSHER_SHAKE_NUM)
        self.alarms["crush_end"] = CRUSHER_CRUSH_TIME

    def event_step(self, time_passed, delta_mult):
        if not self.crushing:
            super(Crusher, self).event_step(time_passed, delta_mult)
            if self.active:
                players = []
                crash_y = sge.game.current_room.height
                objects = (
                    sge.game.current_room.get_objects_at(
                        self.bbox_left - CRUSHER_LAX, self.bbox_bottom,
                        self.bbox_width + 2 * CRUSHER_LAX,
                        (sge.game.current_room.height - self.bbox_bottom +
                         sge.game.current_room.object_area_height)) |
                    sge.game.current_room.object_area_void)
                for obj in objects:
                    if (obj.bbox_top > self.bbox_bottom and
                            self.bbox_right > obj.bbox_left and
                            self.bbox_left < obj.bbox_right):
                        if isinstance(obj, xsge_physics.SolidTop):
                            crash_y = min(crash_y, obj.bbox_top)
                        elif isinstance(obj, xsge_physics.SlopeTopLeft):
                            crash_y = min(crash_y,
                                          obj.get_slope_y(self.bbox_right))
                        elif isinstance(obj, xsge_physics.SlopeTopRight):
                            crash_y = min(crash_y,
                                          obj.get_slope_y(self.bbox_left))
                    if (obj.bbox_top > self.bbox_bottom and
                            self.bbox_right + CRUSHER_LAX > obj.bbox_left and
                            self.bbox_left - CRUSHER_LAX < obj.bbox_right):
                        if isinstance(obj, Player):
                            players.append(obj)

                for player in players:
                    if player.bbox_top < crash_y + CRUSHER_LAX:
                        self.crushing = True
                        self.gravity = CRUSHER_GRAVITY
                        break

    def event_alarm(self, alarm_id):
        if alarm_id == "crush_end":
            self.yvelocity = -CRUSHER_RISE_SPEED

    def event_collision(self, other, xdirection, ydirection):
        if isinstance(other, InteractiveObject) and other.knockable:
            other.knock(self)

        super(Crusher, self).event_collision(other, xdirection, ydirection)


class Circoflame(InteractiveObject):

    killed_by_void = False
    active_range = 0
    burnable = True
    freezable = True

    def __init__(self, center, x, y, z=0, **kwargs):
        self.center = weakref.ref(center)
        kwargs["sprite"] = circoflame_sprite
        kwargs["checks_collisions"] = False
        sge.dsp.Object.__init__(self, x, y, z, **kwargs)

    def touch(self, other):
        other.hurt()

    def freeze(self):
        play_sound(sizzle_sound, self.x, self.y)
        center = self.center()
        if center is not None:
            center.destroy()
        self.destroy()

    def project_light(self):
        xsge_lighting.project_light(self.x, self.y, circoflame_light_sprite)


class CircoflameCenter(InteractiveObject):

    killed_by_void = False
    always_active = True
    never_tangible = True

    def __init__(self, x, y, z=0, radius=(TILE_SIZE * 4), pos=180,
                 rvelocity=2):
        self.radius = radius
        self.pos = pos
        self.rvelocity = rvelocity
        self.flame = Circoflame(self, x, y, z)
        super(CircoflameCenter, self).__init__(x, y, z, visible=False,
                                               tangible=False)

    def event_create(self):
        sge.game.current_room.add(self.flame)

    def event_step(self, time_passed, delta_mult):
        self.pos += self.rvelocity * delta_mult
        self.pos %= 360
        x = math.cos(math.radians(self.pos)) * self.radius
        y = math.sin(math.radians(self.pos)) * self.radius
        self.flame.x = self.x + x
        self.flame.y = self.y + y


class Boss(InteractiveObject):

    def __init__(self, x, y, ID="boss", death_timeline=None, stage=0,
                 **kwargs):
        self.ID = ID
        self.death_timeline = death_timeline
        self.stage = stage
        super(Boss, self).__init__(x, y, **kwargs)

    def event_create(self):
        super(Boss, self).event_create()
        sge.game.current_room.add_timeline_object(self)

    def event_destroy(self):
        for obj in sge.game.current_room.objects:
            if obj is not self and isinstance(obj, Boss) and obj.stage > 0:
                break
        else:
            if self.death_timeline:
                sge.game.current_room.load_timeline(self.death_timeline)


class IceBullet(InteractiveObject, xsge_physics.Collider):

    def deactivate(self):
        self.destroy()

    def dissipate(self):
        if self in sge.game.current_room.objects:
            Smoke.create(self.x, self.y, self.z,
                         sprite=ice_bullet_break_sprite)
            play_sound(icebullet_break_sound, self.x, self.y)
            self.destroy()

    def event_collision(self, other, xdirection, ydirection):
        if ((isinstance(other, InteractiveObject) and other.freezable) or
                isinstance(other, ThinIce)):
            other.freeze()
            self.dissipate()

        super(IceBullet, self).event_collision(other, xdirection, ydirection)

    def event_physics_collision_left(self, other, move_loss):
        self.event_collision(other, -1, 0)
        self.dissipate()

    def event_physics_collision_right(self, other, move_loss):
        self.event_collision(other, 1, 0)
        self.dissipate()

    def event_physics_collision_top(self, other, move_loss):
        self.event_collision(other, 0, -1)
        self.dissipate()

    def event_physics_collision_bottom(self, other, move_loss):
        self.event_collision(other, 0, 1)
        self.dissipate()


class TimelineSwitcher(InteractiveObject):

    def __init__(self, x, y, timeline=None, **kwargs):
        self.timeline = timeline
        kwargs["visible"] = False
        kwargs["checks_collisions"] = False
        sge.dsp.Object.__init__(self, x, y, **kwargs)

    def touch(self, other):
        sge.game.current_room.load_timeline(self.timeline)
        self.destroy()


class Iceblock(xsge_physics.Solid):

    def __init__(self, x, y, **kwargs):
        kwargs["checks_collisions"] = False
        sge.dsp.Object.__init__(self, x, y, **kwargs)

    def burn(self):
        play_sound(sizzle_sound, self.x, self.y)
        Smoke.create(self.x, self.y, self.z, sprite=iceblock_melt_sprite)
        self.destroy()


class BossBlock(InteractiveObject):

    never_active = True
    never_tangible = True

    def __init__(self, x, y, ID=None, **kwargs):
        self.ID = ID
        kwargs["visible"] = False
        sge.dsp.Object.__init__(self, x, y, **kwargs)

    def event_create(self):
        super(BossBlock, self).event_create()
        sge.game.current_room.add_timeline_object(self)

    def activate(self):
        self.child = xsge_physics.Solid.create(
            self.x, self.y, self.z, sprite=boss_block_sprite)
        self.child.x += self.child.image_origin_x
        self.child.y += self.child.image_origin_y
        Smoke.create(self.child.x, self.child.y, z=(self.child.z + 0.5),
                     sprite=item_spawn_cloud_sprite)
        play_sound(pop_sound, self.x, self.y)

    def deactivate(self):
        if self.child is not None:
            Smoke.create(self.child.x, self.child.y, z=self.child.z,
                         sprite=smoke_plume_sprite)
            self.child.destroy()
            self.child = None
            play_sound(pop_sound, self.x, self.y)

    def update_active(self):
        pass


class InfoBlock(HittableBlock, xsge_physics.Solid):

    def __init__(self, x, y, text="(null)", **kwargs):
        super(InfoBlock, self).__init__(x, y, **kwargs)
        self.text = text.replace("\\n", "\n")

    def event_hit_end(self):
        DialogBox(gui_handler, _(self.text), self.sprite).show()


class ThinIce(xsge_physics.Solid):

    def __init__(self, x, y, z=0, permanent=False, **kwargs):
        kwargs["sprite"] = thin_ice_sprite
        kwargs["checks_collisions"] = False
        kwargs["image_fps"] = 0
        sge.dsp.Object.__init__(self, x, y, z, **kwargs)
        self.permanent = permanent
        self.crack_time = 0
        self.freeze_time = 0

    def burn(self):
        self.crack()

    def freeze(self):
        if self.image_index > 0:
            self.image_index -= 1

    def event_step(self, time_passed, delta_mult):
        if self.sprite is thin_ice_sprite:
            players = self.collision(Player, y=(self.y - 1))
            if players:
                if not GOD:
                    for player in players:
                        self.crack_time += delta_mult
                        while self.crack_time >= ICE_CRACK_TIME:
                            self.crack_time -= ICE_CRACK_TIME
                            self.crack()
            elif not self.permanent:
                if self.image_index > 0:
                    rfa = delta_mult * ICE_REFREEZE_RATE
                    self.crack_time -= rfa
                    self.rfa = max(0, -self.crack_time)
                    self.crack_time = max(0, self.crack_time)
                    self.freeze_time += rfa
                    while self.freeze_time >= ICE_CRACK_TIME:
                        self.freeze_time -= ICE_CRACK_TIME
                        if self.image_index > 0:
                            self.image_index -= 1
                else:
                    self.crack_time -= delta_mult * ICE_REFREEZE_RATE
                    self.crack_time = max(0, self.crack_time)

    def event_animation_end(self):
        self.destroy()

    def shatter(self):
        if self.sprite != thin_ice_break_sprite:
            self.sprite = thin_ice_break_sprite
            self.image_index = 0
            self.image_fps = None
            play_sound(ice_shatter_sound, self.x, self.y)

    def crack(self):
        if self.image_index + 1 < self.sprite.frames:
            play_sound(random.choice(ice_crack_sounds), self.x, self.y)
            self.image_index += 1
            self.freeze_time = 0
        else:
            self.shatter()


class Spawn(sge.dsp.Object):

    def __init__(self, x, y, spawn_id=None, **kwargs):
        kwargs["visible"] = False
        kwargs["tangible"] = False
        super(Spawn, self).__init__(x, y, **kwargs)
        self.spawn_id = spawn_id


class Checkpoint(InteractiveObject):

    def __init__(self, x, y, dest=None, **kwargs):
        kwargs["visible"] = False
        super(Checkpoint, self).__init__(x, y, **kwargs)
        self.dest = dest

    def event_create(self):
        if self.dest is not None:
            if ":" not in self.dest:
                self.dest = "{}:{}".format(sge.game.current_room.fname,
                                           self.dest)
        self.reset()

    def reset(self):
        pass

    def touch(self, other):
        global current_checkpoints
        current_checkpoints[main_area] = self.dest

        for obj in sge.game.current_room.objects:
            if isinstance(obj, Checkpoint):
                obj.reset()


class Bell(Checkpoint):

    def __init__(self, x, y, dest=None, **kwargs):
        kwargs["sprite"] = bell_sprite
        InteractiveObject.__init__(self, x, y, **kwargs)
        self.dest = dest

    def reset(self):
        if current_checkpoints.get(main_area) == self.dest:
            self.image_fps = None
        else:
            self.image_fps = 0
            self.image_index = 0

    def touch(self, other):
        super(Bell, self).touch(other)
        play_sound(bell_sound, self.x, self.y)


class Door(sge.dsp.Object):

    def __init__(self, x, y, dest=None, spawn_id=None, **kwargs):
        y += 64
        kwargs["sprite"] = door_sprite
        kwargs["checks_collisions"] = False
        kwargs["image_fps"] = 0
        super(Door, self).__init__(x, y, **kwargs)
        self.dest = dest
        self.spawn_id = spawn_id
        self.occupant = None

    def warp(self, other):
        if self.occupant is None and self.image_index == 0:
            self.occupant = other
            play_sound(door_sound, self.x, self.y)
            self.image_fps = self.sprite.fps

            other.visible = False
            other.tangible = False
            other.warping = True
            other.xvelocity = 0
            other.yvelocity = 0
            other.xacceleration = 0
            other.yacceleration = 0
            other.xdeceleration = 0
            other.ydeceleration = 0

    def warp_end(self):
        warp(self.dest)

    def event_step(self, time_passed, delta_mult):
        if self.occupant is not None:
            s = get_scaled_copy(self.occupant)
            if self.image_fps > 0:
                sge.game.current_room.project_sprite(
                    door_back_sprite, 0, self.x, self.y, self.z - 0.5)
                sge.game.current_room.project_sprite(s, 0, self.x, self.y,
                                                     self.occupant.z)
            else:
                dbs = door_back_sprite.copy()
                dbs.draw_sprite(s, 0, dbs.origin_x, dbs.origin_y)
                sge.game.current_room.project_sprite(dbs, 0, self.x, self.y,
                                                     self.z - 0.5)
        elif self.image_index != 0:
            sge.game.current_room.project_sprite(door_back_sprite, 0, self.x,
                                                 self.y, self.z - 0.5)

    def event_animation_end(self):
        if self.image_fps > 0:
            if self.dest and (':' in self.dest or self.dest == "__map__"):
                self.image_fps = -self.image_fps
                self.image_index = self.sprite.frames - 1
            else:
                self.image_fps = 0
                self.image_index = self.sprite.frames - 1
                self.occupant.visible = True
                self.occupant.tangible = True
                self.occupant.warping = False
                self.occupant.xvelocity = 0
                self.occupant.yvelocity = 0
                self.occupant = None
        elif self.image_fps < 0:
            play_sound(door_shut_sound, self.x, self.y)
            self.image_fps = 0
            self.image_index = 0
            self.occupant = None
            self.warp_end()


class WarpSpawn(xsge_path.Path):

    silent = False

    def __init__(self, x, y, points=(), dest=None, spawn_id=None, **kwargs):
        super(WarpSpawn, self).__init__(x, y, points=points, **kwargs)
        self.dest = dest
        self.spawn_id = spawn_id
        self.direction = None
        self.end_direction = None
        self.warps_out = []

        if points:
            xm, ym = points[0]
            if abs(xm) > abs(ym):
                self.direction = "right" if xm > 0 else "left"
            elif ym:
                self.direction = "down" if ym > 0 else "up"
            else:
                warnings.warn("Warp at position ({}, {}) has no direction".format(x, y))

            if len(points) >= 2:
                x1, y1 = points[-2]
                x2, y2 = points[-1]
                xm = x2 - x1
                ym = y2 - y1
                if abs(xm) > abs(ym):
                    self.end_direction = "right" if xm > 0 else "left"
                elif ym:
                    self.end_direction = "down" if ym > 0 else "up"
                else:
                    warnings.warn("Warp at position ({}, {}) has no end direction".format(x, y))
            else:
                self.end_direction = self.direction

    def event_step(self, time_passed, delta_mult):
        super(WarpSpawn, self).event_step(time_passed, delta_mult)

        x, y = self.points[-1]
        x += self.x
        y += self.y
        finished = []
        for obj in self.warps_out:
            left_edge = obj.x - obj.image_origin_x
            top_edge = obj.y - obj.image_origin_y
            if self.end_direction == "left":
                if obj.bbox_right <= x:
                    obj.bbox_right = x
                    finished.append(obj)
                else:
                    warp_sprite = get_scaled_copy(obj)
                    warp_sprite.draw_erase(
                        math.ceil(x - left_edge), 0, warp_sprite.width,
                        warp_sprite.height)
                    sge.game.current_room.project_sprite(
                        warp_sprite, obj.image_index, obj.x, obj.y, self.z)
            elif self.end_direction == "right":
                if obj.bbox_left >= x:
                    obj.bbox_left = x
                    finished.append(obj)
                else:
                    warp_sprite = get_scaled_copy(obj)
                    warp_sprite.draw_erase(0, 0, math.floor(x - left_edge),
                                           warp_sprite.height)
                    sge.game.current_room.project_sprite(
                        warp_sprite, obj.image_index, obj.x, obj.y, self.z)
            elif self.end_direction == "up":
                if obj.bbox_bottom <= y:
                    obj.bbox_bottom = y
                    finished.append(obj)
                else:
                    warp_sprite = get_scaled_copy(obj)
                    warp_sprite.draw_erase(
                        0, math.ceil(y - top_edge), warp_sprite.width,
                        warp_sprite.height)
                    sge.game.current_room.project_sprite(
                        warp_sprite, obj.image_index, obj.x, obj.y, self.z)
            elif self.end_direction == "down":
                if obj.bbox_top >= y:
                    obj.bbox_top = y
                    finished.append(obj)
                else:
                    warp_sprite = get_scaled_copy(obj)
                    warp_sprite.draw_erase(0, 0, warp_sprite.width,
                                           math.floor(y - top_edge))
                    sge.game.current_room.project_sprite(
                        warp_sprite, obj.image_index, obj.x, obj.y, self.z)

        for obj in finished:
            obj.visible = True
            obj.tangible = True
            obj.warping = False
            obj.speed = 0
            self.warps_out.remove(obj)

    def event_follow_end(self, obj):
        global level_timers
        global score

        if self.dest and (':' in self.dest or self.dest == "__map__"):
            warp(self.dest)
        else:
            if not self.silent:
                play_sound(pipe_sound, obj.x, obj.y)

            self.warps_out.append(obj)
            x, y = self.points[-1]
            x += self.x
            y += self.y
            if self.end_direction == "left":
                obj.x = x + obj.sprite.origin_x
                obj.y = y
                obj.move_direction = 180
            elif self.end_direction == "right":
                obj.x = x + obj.sprite.origin_x - obj.sprite.width
                obj.y = y
                obj.move_direction = 0
            elif self.end_direction == "up":
                obj.x = x
                obj.y = y + obj.sprite.origin_y
                obj.move_direction = 270
            elif self.end_direction == "down":
                obj.x = x
                obj.y = y + obj.sprite.origin_y - obj.sprite.height
                obj.move_direction = 90

            obj.speed = WARP_SPEED
            obj.xacceleration = 0
            obj.yacceleration = 0
            obj.xdeceleration = 0
            obj.ydeceleration = 0


class Warp(WarpSpawn):

    def __init__(self, x, y, **kwargs):
        super(Warp, self).__init__(x, y, **kwargs)
        self.warps_in = []

    def warp(self, other):
        if not self.silent:
            play_sound(pipe_sound, other.x, other.y)

        self.warps_in.append(other)

        if getattr(other, "held_object") is not None:
            other.held_object.drop()

        other.visible = False
        other.tangible = False
        other.warping = True
        other.move_direction = {"right": 0, "up": 270, "left": 180,
                                "down": 90}.get(self.direction, 0)
        other.speed = WARP_SPEED
        other.xacceleration = 0
        other.yacceleration = 0
        other.xdeceleration = 0
        other.ydeceleration = 0

    def event_create(self):
        if self not in sge.game.current_room.warps:
            sge.game.current_room.warps.append(self)

    def event_end_step(self, time_passed, delta_mult):
        super(Warp, self).event_step(time_passed, delta_mult)

        finished = []
        for obj in self.warps_in:
            left_edge = obj.x - obj.image_origin_x
            top_edge = obj.y - obj.image_origin_y
            if self.direction == "left":
                if obj.x <= self.x + obj.image_origin_x - obj.sprite.width:
                    finished.append(obj)
                else:
                    warp_sprite = get_scaled_copy(obj)
                    warp_sprite.draw_erase(
                        0, 0, math.floor(self.x - left_edge),
                        warp_sprite.height)
                    sge.game.current_room.project_sprite(
                        warp_sprite, obj.image_index, obj.x, obj.y, self.z)
            elif self.direction == "right":
                if obj.x >= self.x + obj.image_origin_x:
                    finished.append(obj)
                else:
                    warp_sprite = get_scaled_copy(obj)
                    warp_sprite.draw_erase(
                        math.ceil(self.x - left_edge), 0, warp_sprite.width,
                        warp_sprite.height)
                    sge.game.current_room.project_sprite(
                        warp_sprite, obj.image_index, obj.x, obj.y, self.z)
            elif self.direction == "up":
                if obj.y <= self.y + obj.image_origin_y - obj.sprite.height:
                    finished.append(obj)
                else:
                    warp_sprite = get_scaled_copy(obj)
                    warp_sprite.draw_erase(0, 0, warp_sprite.width,
                                           math.floor(self.y - top_edge))
                    sge.game.current_room.project_sprite(
                        warp_sprite, obj.image_index, obj.x, obj.y, self.z)
            elif self.direction == "down":
                if obj.y >= self.y + obj.image_origin_y:
                    finished.append(obj)
                else:
                    warp_sprite = get_scaled_copy(obj)
                    warp_sprite.draw_erase(
                        0, math.ceil(self.y - top_edge), warp_sprite.width,
                        warp_sprite.height)
                    sge.game.current_room.project_sprite(
                        warp_sprite, obj.image_index, obj.x, obj.y, self.z)

        for obj in finished:
            obj.x = self.x
            obj.y = self.y
            self.follow_start(obj, WARP_SPEED)
            self.warps_in.remove(obj)

    def event_destroy(self):
        while self in sge.game.current_room.warps:
            sge.game.current_room.warps.remove(self)


class ObjectWarpSpawn(WarpSpawn):

    def __init__(self, x, y, points=(), cls=None, interval=180, limit=None,
                 silent=False, **kwargs):
        self.cls = TYPES.get(cls)
        self.kwargs = kwargs
        self.interval = interval
        self.limit = limit
        self.silent = silent
        self.__steps_passed = interval
        self.__objects = []
        super(ObjectWarpSpawn, self).__init__(x, y, points=points)

    def event_begin_step(self, time_passed, delta_mult):
        in_view = False
        for view in sge.game.current_room.views:
            if (self.x <= view.x + view.width and self.x >= view.x and
                    self.y <= view.y + view.height and self.y >= view.y):
                in_view = True
                break

        if in_view and self.cls is not None:
            self.__steps_passed += delta_mult
            
            self.__objects = [ref for ref in self.__objects
                              if (ref() is not None and
                                  ref() in sge.game.current_room.objects)]
            if self.limit and len(self.__objects) >= self.limit:
                self.__steps_passed = 0

            while self.__steps_passed >= self.interval:
                self.__steps_passed -= self.interval
                obj = self.cls.create(self.x, self.y, **self.kwargs)
                obj.activate()
                obj.warping = True
                obj.visible = False
                obj.tangible = False
                self.follow_start(obj, WARP_SPEED)
                self.__objects.append(weakref.ref(obj))


class MovingObjectPath(xsge_path.PathLink):

    cls = None
    default_speed = ENEMY_WALK_SPEED
    default_accel = None
    default_decel = None
    default_loop = None
    auto_follow = True

    def __init__(self, x, y, path_speed=None, path_accel=None, path_decel=None,
                 path_loop=None, path_id=None, prime=False, parent=None,
                 **kwargs):
        if path_speed is None:
            path_speed = self.default_speed
        if path_accel is None:
            path_accel = self.default_accel
        if path_decel is None:
            path_decel = self.default_decel
        if path_loop is None:
            path_loop = self.default_loop

        self.path_speed = path_speed
        self.path_accel = path_accel if path_accel != -1 else None
        self.path_decel = path_decel if path_decel != -1 else None
        self.path_loop = path_loop if path_loop != -1 else None
        self.path_id = path_id
        self.prime = prime
        self.parent = parent
        self.obj = lambda: None
        super(MovingObjectPath, self).__init__(x, y, **kwargs)

    def event_create(self):
        if self.parent is not None:
            for obj in sge.game.current_room.objects:
                if (isinstance(obj, self.__class__) and
                        obj.path_id == self.parent):
                    obj.next_path = self
                    obj.next_speed = self.path_speed
                    obj.next_accel = self.path_accel
                    obj.next_decel = self.path_decel
                    obj.next_loop = self.path_loop
                    break
        else:
            self.prime = True

        if self.prime and self.cls in TYPES:
            obj = TYPES[self.cls].create(self.x, self.y, z=self.z)
            self.obj = weakref.ref(obj)
            if self.auto_follow:
                self.follow_start(obj, self.path_speed, accel=self.path_accel,
                                  decel=self.path_decel, loop=self.path_loop)


class MovingPlatformPath(MovingObjectPath):

    cls = "moving_platform"
    default_speed = 3
    default_accel = 0.02
    default_decel = 0.02

    def event_create(self):
        super(MovingPlatformPath, self).event_create()
        obj = self.obj()
        if obj:
            obj.path = self

    def follow_start(self, obj, *args, **kwargs):
        super(MovingPlatformPath, self).follow_start(obj, *args, **kwargs)
        obj.following = True

    def event_follow_end(self, obj):
        obj.following = False
        obj.speed = 0
        obj.x = self.x + self.points[-1][0]
        obj.y = self.y + self.points[-1][1]


class TriggeredMovingPlatformPath(MovingPlatformPath):

    default_speed = 2
    default_accel = None
    default_decel = None
    auto_follow = False
    followed = False


class CircoflamePath(xsge_path.Path):

    def __init__(self, x, y, z=0, points=(), rvelocity=2):
        self.rvelocity = rvelocity
        x += TILE_SIZE / 2
        y += TILE_SIZE / 2
        super(CircoflamePath, self).__init__(x, y, z=z, points=points)

    def event_create(self):
        if self.points:
            fx, fy = self.points[0]
            radius = math.hypot(fx, fy)
            pos = math.degrees(math.atan2(fy, fx))
            CircoflameCenter.create(self.x, self.y, z=self.z, radius=radius,
                                    pos=pos, rvelocity=self.rvelocity)
        self.destroy()


class Menu(xsge_gui.MenuWindow):

    items = []

    @classmethod
    def create(cls, default=0):
        if cls.items:
            self = cls.from_text(
                gui_handler, sge.game.width / 2, sge.game.height * 2 / 3,
                cls.items, font_normal=font,
                color_normal=sge.gfx.Color("white"),
                color_selected=sge.gfx.Color((0, 128, 255)),
                background_color=menu_color, margin=9, halign="center",
                valign="middle")
            default %= len(self.widgets)
            self.keyboard_focused_widget = self.widgets[default]
            self.show()
            return self

    def event_change_keyboard_focus(self):
        play_sound(select_sound)


class MainMenu(Menu):

    items = [_("New Game"), _("Load Game"), _("Select Levelset"), _("Options"),
             _("Credits"), _("Quit")]

    def event_choose(self):
        if self.choice == 0:
            play_sound(confirm_sound)
            NewGameMenu.create_page()
        elif self.choice == 1:
            play_sound(confirm_sound)
            LoadGameMenu.create_page()
        elif self.choice == 2:
            play_sound(confirm_sound)
            LevelsetMenu.create_page(refreshlist=True)
        elif self.choice == 3:
            play_sound(confirm_sound)
            OptionsMenu.create_page()
        elif self.choice == 4:
            credits_room = CreditsScreen.load(os.path.join("special",
                                                           "credits.tmx"))
            credits_room.start()
        else:
            sge.game.end()


class NewGameMenu(Menu):

    @classmethod
    def create_page(cls, default=0):
        cls.items = []
        for slot in save_slots:
            if slot is None:
                cls.items.append(_("-Empty-"))
            elif slot.get("levelset") is None:
                cls.items.append(_("-No Levelset-"))
            else:
                fname = os.path.join(DATA, "levelsets", slot["levelset"])
                try:
                    with open(fname, 'r') as f:
                        data = json.load(f)
                except (IOError, ValueError):
                    cls.items.append(_("-Corrupt Levelset-"))
                    continue
                else:
                    levelset_name = data.get("name", slot["levelset"])
                    completion = slot.get("completion", 0)
                    cls.items.append("{} ({}%)".format(levelset_name,
                                                       completion))

        cls.items.append(_("Back"))

        return cls.create(default)

    def event_choose(self):
        global abort
        global current_save_slot

        abort = False

        if self.choice in six.moves.range(len(save_slots)):
            play_sound(confirm_sound)
            current_save_slot = self.choice
            if save_slots[current_save_slot] is None:
                set_new_game()
                if not abort:
                    start_levelset()
                else:
                    NewGameMenu.create(default=self.choice)
            else:
                OverwriteConfirmMenu.create(default=1)
        else:
            play_sound(cancel_sound)
            MainMenu.create(default=0)


class OverwriteConfirmMenu(Menu):

    items = [_("Overwrite this save file"), _("Cancel")]

    def event_choose(self):
        global abort

        abort = False

        if self.choice == 0:
            play_sound(confirm_sound)
            set_new_game()
            if not abort:
                start_levelset()
            else:
                play_sound(cancel_sound)
                NewGameMenu.create(default=current_save_slot)
        else:
            play_sound(cancel_sound)
            NewGameMenu.create(default=current_save_slot)


class LoadGameMenu(NewGameMenu):

    def event_choose(self):
        global abort
        global current_save_slot

        abort = False

        if self.choice in six.moves.range(len(save_slots)):
            play_sound(confirm_sound)
            current_save_slot = self.choice
            load_game()
            if abort:
                MainMenu.create(default=1)
            elif not start_levelset():
                play_sound(error_sound)
                show_error(_("An error occurred when trying to load the game."))
                MainMenu.create(default=1)
        else:
            play_sound(cancel_sound)
            MainMenu.create(default=1)


class LevelsetMenu(Menu):

    levelsets = []
    current_levelsets = []
    page = 0

    @classmethod
    def create_page(cls, default=0, page=0, refreshlist=False):
        if refreshlist or not cls.levelsets:
            cls.levelsets = []
            for fname in os.listdir(os.path.join(DATA, "levelsets")):
                try:
                    with open(os.path.join(DATA, "levelsets", fname), 'r') as f:
                        data = json.load(f)
                except (IOError, ValueError):
                    continue
                else:
                    cls.levelsets.append((fname, str(data.get("name", "???"))))

            def sort_key(T):
                # The current levelset has top priority, followed by the
                # ReTux levelset, and every other levelset is sorted
                # alphabetically based first on their displayed names
                # and secondly on their file names.
                return (T[0] != current_levelset, T[0] != "retux.json",
                        T[1].lower(), T[0].lower())
            cls.levelsets.sort(key=sort_key)

        cls.current_levelsets = []
        cls.items = []
        if cls.levelsets:
            page_size = MENU_MAX_ITEMS - 2
            n_pages = math.ceil(len(cls.levelsets) / page_size)
            page = int(page % n_pages)
            page_start = page * page_size
            page_end = min(page_start + page_size, len(cls.levelsets))
            current_page = cls.levelsets[page_start:page_end]
            cls.current_levelsets = []
            cls.items = []
            for fname, name in current_page:
                cls.current_levelsets.append(fname)
                cls.items.append(name)

        cls.items.append(_("Next page"))
        cls.items.append(_("Back"))

        self = cls.create(default)
        self.page = page
        return self

    def event_choose(self):
        if self.choice == len(self.items) - 2:
            play_sound(select_sound)
            self.create_page(default=-2, page=self.page)
        else:
            if self.choice is not None and self.choice < len(self.items) - 2:
                play_sound(confirm_sound)
                load_levelset(self.current_levelsets[self.choice])
            else:
                play_sound(cancel_sound)

            MainMenu.create(default=2)


class OptionsMenu(Menu):

    @classmethod
    def create_page(cls, default=0):
        smt = scale_method if scale_method else "fastest"
        cls.items = [
            _("Fullscreen: {}").format(_("On") if fullscreen else _("Off")),
            _("Scale Method: {}").format(smt),
            _("Sound: {}").format(_("On") if sound_enabled else _("Off")),
            _("Music: {}").format(_("On") if music_enabled else _("Off")),
            _("Stereo: {}").format(_("On") if stereo_enabled else _("Off")),
            _("Show FPS: {}").format(_("On") if fps_enabled else _("Off")),
            _("Joystick Threshold: {}%").format(int(joystick_threshold * 100)),
            _("Configure keyboard"), _("Configure joysticks"),
            _("Detect joysticks"), _("Import levelset"), _("Export levelset"),
            _("Back")]
        return cls.create(default)

    def event_choose(self):
        global fullscreen
        global scale_method
        global sound_enabled
        global music_enabled
        global stereo_enabled
        global fps_enabled
        global joystick_threshold

        if self.choice == 0:
            play_sound(select_sound)
            fullscreen = not fullscreen
            sge.game.fullscreen = fullscreen
            OptionsMenu.create_page(default=self.choice)
        elif self.choice == 1:
            choices = [None, "noblur", "smooth"] + sge.SCALE_METHODS
            if scale_method in choices:
                i = choices.index(scale_method)
            else:
                i = 0

            play_sound(select_sound)
            i += 1
            i %= len(choices)
            scale_method = choices[i]
            sge.game.scale_method = scale_method
            OptionsMenu.create_page(default=self.choice)
        elif self.choice == 2:
            sound_enabled = not sound_enabled
            play_sound(bell_sound)
            OptionsMenu.create_page(default=self.choice)
        elif self.choice == 3:
            music_enabled = not music_enabled
            play_music(sge.game.current_room.music)
            OptionsMenu.create_page(default=self.choice)
        elif self.choice == 4:
            stereo_enabled = not stereo_enabled
            play_sound(confirm_sound)
            OptionsMenu.create_page(default=self.choice)
        elif self.choice == 5:
            play_sound(select_sound)
            fps_enabled = not fps_enabled
            OptionsMenu.create_page(default=self.choice)
        elif self.choice == 6:
            play_sound(select_sound)
            # This somewhat complicated method is to prevent rounding
            # irregularities.
            threshold = ((int(joystick_threshold * 100) + 5) % 100) / 100
            if not threshold:
                threshold = 0.0001
            joystick_threshold = threshold
            xsge_gui.joystick_threshold = threshold
            OptionsMenu.create_page(default=self.choice)
        elif self.choice == 7:
            play_sound(confirm_sound)
            KeyboardMenu.create_page()
        elif self.choice == 8:
            play_sound(confirm_sound)
            JoystickMenu.create_page()
        elif self.choice == 9:
            sge.joystick.refresh()
            play_sound(heal_sound)
            OptionsMenu.create_page(default=self.choice)
        elif self.choice == 10:
            if HAVE_TK:
                play_sound(confirm_sound)
                fname = tkinter_filedialog.askopenfilename(
                    filetypes=[(_("ReTux levelset files"), ".rtz"),
                               (_("all files"), ".*")])

                w = 400
                h = 128
                margin = 16
                x = SCREEN_SIZE[0] / 2 - w / 2
                y = SCREEN_SIZE[1] / 2 - h / 2
                c = sge.gfx.Color("black")
                window = xsge_gui.Window(gui_handler, x, y, w, h,
                                         background_color=c, border=False)

                x = margin
                y = margin
                text = _("Importing levelset...")
                c = sge.gfx.Color("white")
                xsge_gui.Label(
                    window, x, y, 1, text, font=font, width=(w - 2 * margin),
                    height=(h - 3 * margin -
                            xsge_gui.progressbar_container_sprite.height),
                    color=c)

                x = margin
                y = h - margin - xsge_gui.progressbar_container_sprite.height
                progressbar = xsge_gui.ProgressBar(window, x, y, 0,
                                                   width=(w - 2 * margin))

                window.show()
                gui_handler.event_step(0, 0)
                sge.game.refresh()

                with zipfile.ZipFile(fname, 'r') as rtz:
                    infolist = rtz.infolist()
                    for i in six.moves.range(len(infolist)):
                        member = infolist[i]
                        rtz.extract(member, DATA)
                        rtz.extract(member, os.path.join(CONFIG, "data"))
                        progressbar.progress = (i + 1) / len(infolist)
                        progressbar.redraw()
                        sge.game.pump_input()
                        gui_handler.event_step(0, 0)
                        sge.game.refresh()

                window.destroy()
                sge.game.pump_input()
                gui_handler.event_step(0, 0)
                sge.game.refresh()
                sge.game.pump_input()
                sge.game.input_events = []
            else:
                play_sound(kill_sound)
                e = _("This feature requires Tkinter, which was not successfully imported. Please make sure Tkinter is installed and try again.")
                show_error(e)
            OptionsMenu.create_page(default=self.choice)
        elif self.choice == 11:
            if HAVE_TK:
                play_sound(confirm_sound)
                ExportLevelsetMenu.create_page(refreshlist=True)
            else:
                play_sound(kill_sound)
                e = _("This feature requires Tkinter, which was not successfully imported. Please make sure Tkinter is installed and try again.")
                show_error(e)
                OptionsMenu.create_page(default=self.choice)
        else:
            play_sound(cancel_sound)
            write_to_disk()
            MainMenu.create(default=3)


class KeyboardMenu(Menu):

    page = 0

    @classmethod
    def create_page(cls, default=0, page=0):
        page %= min(len(left_key), len(right_key), len(up_key), len(down_key),
                    len(halt_key), len(jump_key), len(shoot_key),
                    len(aim_up_key), len(aim_down_key), len(mode_reset_key),
                    len(mode_key), len(pause_key))

        def format_key(key):
            if key:
                return " ".join(key)
            else:
                return None

        cls.items = [_("Player {}").format(page + 1),
                     _("Left: {}").format(format_key(left_key[page])),
                     _("Right: {}").format(format_key(right_key[page])),
                     _("Up: {}").format(format_key(up_key[page])),
                     _("Down: {}").format(format_key(down_key[page])),
                     _("Halt: {}").format(format_key(halt_key[page])),
                     _("Jump: {}").format(format_key(jump_key[page])),
                     _("Shoot: {}").format(format_key(shoot_key[page])),
                     _("Aim Up: {}").format(format_key(aim_up_key[page])),
                     _("Aim Down: {}").format(format_key(aim_down_key[page])),
                     _("Reset Mode: {}").format(format_key(mode_reset_key[page])),
                     _("Mode: {}").format(format_key(mode_key[page])),
                     _("Pause: {}").format(format_key(pause_key[page])),
                     _("Back")]
        self = cls.create(default)
        self.page = page
        return self

    def event_choose(self):
        def toggle_key(key, new_key):
            if new_key in key:
                key.remove(new_key)
            else:
                key.append(new_key)
                while len(key) > 2:
                    key.pop(0)

        if self.choice == 0:
            play_sound(select_sound)
            KeyboardMenu.create_page(default=self.choice, page=(self.page + 1))
        elif self.choice == 1:
            k = wait_key()
            if k is not None:
                toggle_key(left_key[self.page], k)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            KeyboardMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 2:
            k = wait_key()
            if k is not None:
                toggle_key(right_key[self.page], k)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            KeyboardMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 3:
            k = wait_key()
            if k is not None:
                toggle_key(up_key[self.page], k)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            KeyboardMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 4:
            k = wait_key()
            if k is not None:
                toggle_key(down_key[self.page], k)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            KeyboardMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 5:
            k = wait_key()
            if k is not None:
                toggle_key(halt_key[self.page], k)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            KeyboardMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 6:
            k = wait_key()
            if k is not None:
                toggle_key(jump_key[self.page], k)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            KeyboardMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 7:
            k = wait_key()
            if k is not None:
                toggle_key(shoot_key[self.page], k)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            KeyboardMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 8:
            k = wait_key()
            if k is not None:
                toggle_key(aim_up_key[self.page], k)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            KeyboardMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 9:
            k = wait_key()
            if k is not None:
                toggle_key(aim_down_key[self.page], k)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            KeyboardMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 10:
            k = wait_key()
            if k is not None:
                toggle_key(mode_reset_key[self.page], k)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            KeyboardMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 11:
            k = wait_key()
            if k is not None:
                toggle_key(mode_key[self.page], k)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            KeyboardMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 12:
            k = wait_key()
            if k is not None:
                toggle_key(pause_key[self.page], k)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            KeyboardMenu.create_page(default=self.choice, page=self.page)
        else:
            play_sound(cancel_sound)
            OptionsMenu.create_page(default=5)


class JoystickMenu(Menu):

    page = 0

    @classmethod
    def create_page(cls, default=0, page=0):
        page %= min(len(left_js), len(right_js), len(up_js), len(down_js),
                    len(halt_js), len(jump_js), len(shoot_js),
                    len(aim_up_js), len(aim_down_js), len(mode_reset_js),
                    len(mode_js), len(pause_js))

        def format_js(js):
            js_template = "{},{},{}"
            sL = []
            for j in js:
                sL.append(js_template.format(*j))
            if sL:
                return " ".join(sL)
            else:
                return _("None")

        cls.items = [_("Player {}").format(page + 1),
                     _("Left: {}").format(format_js(left_js[page])),
                     _("Right: {}").format(format_js(right_js[page])),
                     _("Up: {}").format(format_js(up_js[page])),
                     _("Down: {}").format(format_js(down_js[page])),
                     _("Halt: {}").format(format_js(halt_js[page])),
                     _("Jump: {}").format(format_js(jump_js[page])),
                     _("Shoot: {}").format(format_js(shoot_js[page])),
                     _("Aim Up: {}").format(format_js(aim_up_js[page])),
                     _("Aim Down: {}").format(format_js(aim_down_js[page])),
                     _("Reset Mode: {}").format(format_js(mode_reset_js[page])),
                     _("Mode: {}").format(format_js(mode_js[page])),
                     _("Pause: {}").format(format_js(pause_js[page])),
                     _("Back")]
        self = cls.create(default)
        self.page = page
        return self

    def event_choose(self):
        def toggle_js(js, new_js):
            if new_js in js:
                js.remove(new_js)
            else:
                js.append(new_js)
                while len(js) > 2:
                    js.pop(0)

        if self.choice == 0:
            play_sound(select_sound)
            JoystickMenu.create_page(default=self.choice, page=(self.page + 1))
        elif self.choice == 1:
            js = wait_js()
            if js is not None:
                toggle_js(left_js[self.page], js)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            JoystickMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 2:
            js = wait_js()
            if js is not None:
                toggle_js(right_js[self.page], js)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            JoystickMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 3:
            js = wait_js()
            if js is not None:
                toggle_js(up_js[self.page], js)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            JoystickMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 4:
            js = wait_js()
            if js is not None:
                toggle_js(down_js[self.page], js)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            JoystickMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 5:
            js = wait_js()
            if js is not None:
                toggle_js(halt_js[self.page], js)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            JoystickMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 6:
            js = wait_js()
            if js is not None:
                toggle_js(jump_js[self.page], js)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            JoystickMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 7:
            js = wait_js()
            if js is not None:
                toggle_js(shoot_js[self.page], js)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            JoystickMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 8:
            js = wait_js()
            if js is not None:
                toggle_js(aim_up_js[self.page], js)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            JoystickMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 9:
            js = wait_js()
            if js is not None:
                toggle_js(aim_down_js[self.page], js)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            JoystickMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 10:
            js = wait_js()
            if js is not None:
                toggle_js(mode_reset_js[self.page], js)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            JoystickMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 11:
            js = wait_js()
            if js is not None:
                toggle_js(mode_js[self.page], js)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            JoystickMenu.create_page(default=self.choice, page=self.page)
        elif self.choice == 12:
            js = wait_js()
            if js is not None:
                toggle_js(pause_js[self.page], js)
                set_gui_controls()
                play_sound(confirm_sound)
            else:
                play_sound(cancel_sound)
            JoystickMenu.create_page(default=self.choice, page=self.page)
        else:
            play_sound(cancel_sound)
            OptionsMenu.create_page(default=6)


class ExportLevelsetMenu(LevelsetMenu):

    def event_choose(self):
        if self.choice == len(self.items) - 2:
            play_sound(select_sound)
            self.create_page(default=-2, page=self.page)
        else:
            if self.choice is not None and self.choice < len(self.items) - 2:
                play_sound(confirm_sound)

                fname = tkinter_filedialog.asksaveasfilename(
                    defaultextension=".rtz",
                    filetypes=[(_("ReTux levelset files"), ".rtz"),
                               (_("all files"), ".*")])

                w = 400
                h = 128
                margin = 16
                x = SCREEN_SIZE[0] / 2 - w / 2
                y = SCREEN_SIZE[1] / 2 - h / 2
                c = sge.gfx.Color("black")
                window = xsge_gui.Window(gui_handler, x, y, w, h,
                                         background_color=c, border=False)

                x = margin
                y = margin
                text = _("Exporting levelset...")
                c = sge.gfx.Color("white")
                xsge_gui.Label(
                    window, x, y, 1, text, font=font, width=(w - 2 * margin),
                    height=(h - 3 * margin -
                            xsge_gui.progressbar_container_sprite.height),
                    color=c)

                x = margin
                y = h - margin - xsge_gui.progressbar_container_sprite.height
                progressbar = xsge_gui.ProgressBar(window, x, y, 0,
                                                   width=(w - 2 * margin))

                window.show()
                gui_handler.event_step(0, 0)
                sge.game.refresh()

                levelset = self.current_levelsets[self.choice]
                levelset_fname = os.path.join(DATA, "levelsets", levelset)
                with open(levelset_fname, 'r') as f:
                    data = json.load(f)
                start_cutscene = data.get("start_cutscene")
                worldmap = data.get("worldmap")
                levels = data.get("levels", [])
                include_files = data.get("include_files", [])

                def get_extra_files(fd, exclude_files):
                    if fd in exclude_files:
                        return set()

                    tmx_dir = os.path.relpath(os.path.dirname(fd), DATA)
                    extra_files = {fd}
                    exclude_files.add(fd)
                    try:
                        tilemap = tmx.TileMap.load(fd)
                    except IOError as e:
                        show_error(str(e))
                        return extra_files

                    for prop in tilemap.properties:
                        if prop.name == "music":
                            extra_files.add(os.path.join(DATA, "music",
                                                         prop.value))
                        elif prop.name == "timeline":
                            extra_files.add(os.path.join(DATA, "timelines",
                                                         prop.value))

                    for tileset in tilemap.tilesets:
                        ts_dir = tmx_dir
                        if tileset.source is not None:
                            extra_files.add(os.path.join(DATA, tmx_dir,
                                                         tileset.source))
                            ts_dir = os.path.dirname(os.path.join(
                                tmx_dir, tileset.source))

                        if (tileset.image is not None and
                                tileset.image.source is not None):
                            extra_files.add(os.path.join(DATA, ts_dir,
                                                         tileset.image.source))

                    def check_obj(cls, properties, exclude_files,
                                  get_extra_files=get_extra_files):
                        if cls == get_object:
                            for prop in properties:
                                if prop.name == "cls":
                                    cls = TYPES.get(prop.value,
                                                    xsge_tmx.Decoration)

                        extra_files = set()
                        for prop in properties:
                            if prop.name == "dest":
                                if ":" in prop.value:
                                    level_f, _ = prop.value.split(':', 1)
                                elif cls in {Warp, MapWarp}:
                                    level_f = prop.value
                                else:
                                    level_f = None

                                if level_f and level_f not in {
                                        "__main__", "__map__"}:
                                    if cls == MapWarp:
                                        sdir = "worldmaps"
                                    else:
                                        sdir = "levels"

                                    fname = os.path.join(DATA, sdir, level_f)
                                    extra_files |= get_extra_files(
                                        fname, exclude_files)
                            elif prop.name.endswith("timeline"):
                                extra_files.add(
                                    os.path.join(DATA, "timelines", prop.value))
                            elif prop.name == "level":
                                fname = os.path.join(DATA, "levels",
                                                     prop.value)
                                extra_files |= get_extra_files(fname,
                                                               exclude_files)

                        return extra_files

                    for layer in tilemap.layers:
                        if isinstance(layer, tmx.Layer):
                            layer_cls = TYPES.get(layer.name)
                            layer_prop = layer.properties
                            for tile in layer.tiles:
                                if tile.gid:
                                    tile_ts = None
                                    for ts in sorted(tilemap.tilesets,
                                                     key=lambda x: x.firstgid):
                                        if ts.firstgid <= tile.gid:
                                            tile_ts = ts
                                        else:
                                            break

                                    if tile_ts is not None:
                                        ts_cls = TYPES.get(tile_ts.name)
                                        ts_prop = tile_ts.properties
                                        tile_prop = []
                                        i = tile.gid - tile_ts.firstgid
                                        for tile_def in tile_ts.tiles:
                                            if tile_def.id == i:
                                                tile_prop = tile_def.properties
                                                break
                                        cls = ts_cls or layer_cls
                                        prop = layer_prop + ts_prop + tile_prop
                                        extra_files |= check_obj(cls, prop,
                                                                 exclude_files)
                        elif isinstance(layer, tmx.ObjectGroup):
                            layer_cls = TYPES.get(layer.name)
                            layer_prop = layer.properties
                            for obj in layer.objects:
                                cls = TYPES.get(obj.name) or TYPES.get(obj.type)
                                prop = obj.properties
                                if obj.gid:
                                    obj_ts = None
                                    for ts in sorted(tilemap.tilesets,
                                                     key=lambda x: x.firstgid):
                                        if ts.firstgid <= obj.gid:
                                            obj_ts = ts
                                        else:
                                            break

                                    if obj_ts is not None:
                                        ts_cls = TYPES.get(obj_ts.name)
                                        ts_prop = obj_ts.properties
                                        tile_prop = []
                                        i = obj.gid - obj_ts.firstgid
                                        for tile_def in obj_ts.tiles:
                                            if tile_def.id == i:
                                                tile_prop = tile_def.properties
                                                break
                                        cls = cls or ts_cls
                                        prop = tile_prop + prop
                                cls = cls or layer_cls
                                prop = layer_prop + prop
                                extra_files |= check_obj(cls, prop,
                                                         exclude_files)
                        elif isinstance(layer, tmx.ImageLayer):
                            extra_files |= check_obj(TYPES.get(layer.name),
                                                     layer.properties,
                                                     exclude_files)
                            if (layer.image is not None and
                                    layer.image.source is not None):
                                extra_files.add(
                                    os.path.join(DATA, tmx_dir,
                                                 layer.image.source))

                    return extra_files

                files = {levelset_fname}
                exclude_files = set()
                if start_cutscene:
                    fd = os.path.join(DATA, "levels", start_cutscene)
                    files |= get_extra_files(fd, exclude_files)
                if worldmap:
                    fd = os.path.join(DATA, "worldmaps", worldmap)
                    files |= get_extra_files(fd, exclude_files)
                for level in levels:
                    fd = os.path.join(DATA, "levels", level)
                    files |= get_extra_files(fd, exclude_files)
                for include_file in include_files:
                    files.add(os.path.join(DATA, include_file))

                files = list(files)
                inst_dir = os.path.join(os.path.dirname(__file__), "data")

                with zipfile.ZipFile(fname, 'w') as rtz:
                    for i in six.moves.range(len(files)):
                        fname = files[i]
                        aname = os.path.relpath(fname, DATA)
                        if not os.path.exists(os.path.join(inst_dir, aname)):
                            rtz.write(fname, aname)

                        progressbar.progress = (i + 1) / len(files)
                        progressbar.redraw()
                        sge.game.pump_input()
                        gui_handler.event_step(0, 0)
                        sge.game.refresh()

                window.destroy()
                sge.game.pump_input()
                gui_handler.event_step(0, 0)
                sge.game.refresh()
                sge.game.pump_input()
                sge.game.input_events = []
            else:
                play_sound(cancel_sound)

            OptionsMenu.create(default=10)


class ModalMenu(xsge_gui.MenuDialog):

    items = []

    @classmethod
    def create(cls, default=0):
        if cls.items:
            self = cls.from_text(
                gui_handler, sge.game.width / 2, sge.game.height / 2,
                cls.items, font_normal=font,
                color_normal=sge.gfx.Color("white"),
                color_selected=sge.gfx.Color((0, 128, 255)),
                background_color=menu_color, margin=9, halign="center",
                valign="middle")
            default %= len(self.widgets)
            self.keyboard_focused_widget = self.widgets[default]
            self.show()
            return self

    def event_change_keyboard_focus(self):
        play_sound(select_sound)


class PauseMenu(ModalMenu):

    @classmethod
    def create(cls, default=0):
        if LEVEL or RECORD:
            items = [_("Continue"), _("Abort")]
        elif current_worldmap:
            items = [_("Continue"), _("Return to Map"),
                     _("Return to Title Screen")]
        else:
            items = [_("Continue"), _("Return to Title Screen")]

        self = cls.from_text(
            gui_handler, sge.game.width / 2, sge.game.height / 2,
            items, font_normal=font, color_normal=sge.gfx.Color("white"),
            color_selected=sge.gfx.Color((0, 128, 255)),
            background_color=menu_color, margin=9, halign="center",
            valign="middle")
        default %= len(self.widgets)
        self.keyboard_focused_widget = self.widgets[default]
        self.show()
        return self

    def event_choose(self):
        sge.snd.Music.unpause()

        if self.choice == 1:
            rush_save()
            if current_worldmap:
                play_sound(kill_sound)

            sge.game.current_room.return_to_map()
        elif self.choice == 2:
            rush_save()
            sge.game.start_room.start()
        else:
            play_sound(select_sound)


class WorldmapMenu(ModalMenu):

    items = [_("Continue"), _("Return to Title Screen")]

    def event_choose(self):
        sge.snd.Music.unpause()

        if self.choice == 1:
            rush_save()
            sge.game.start_room.start()
        else:
            play_sound(select_sound)


class DialogLabel(xsge_gui.ProgressiveLabel):

    def event_add_character(self):
        if self.text[-1] not in (' ', '\n', '\t'):
            play_sound(type_sound)


class DialogBox(xsge_gui.Dialog):

    def __init__(self, parent, text, portrait=None, rate=TEXT_SPEED):
        width = sge.game.width / 2
        x_padding = 16
        y_padding = 16
        label_x = 8
        label_y = 8
        if portrait is not None:
            x_padding += 8
            label_x += 8
            portrait_w = portrait.width
            portrait_h = portrait.height
            label_x += portrait_w
        else:
            portrait_w = 0
            portrait_h = 0
        label_w = max(1, width - portrait_w - x_padding)
        height = max(1, portrait_h + y_padding,
                     font.get_height(text, width=label_w) + y_padding)
        x = sge.game.width / 2 - width / 2
        y = sge.game.height / 2 - height / 2
        super(DialogBox, self).__init__(
            parent, x, y, width, height,
            background_color=menu_color, border=False)
        label_h = max(1, height - y_padding)

        self.label = DialogLabel(self, label_x, label_y, 0, text, font=font,
                                 width=label_w, height=label_h,
                                 color=sge.gfx.Color("white"), rate=rate)

        if portrait is not None:
            xsge_gui.Widget(self, 8, 8, 0, sprite=portrait)

    def event_press_enter(self):
        if len(self.label.text) < len(self.label.full_text):
            self.label.text = self.label.full_text
        else:
            self.destroy()

    def event_press_escape(self):
        self.destroy()
        room = sge.game.current_room
        if (isinstance(room, Level) and
                room.timeline_skip_target is not None and
                room.timeline_step < room.timeline_skip_target):
            room.timeline_skipto(room.timeline_skip_target)


def get_object(x, y, cls=None, **kwargs):
    cls = TYPES.get(cls, xsge_tmx.Decoration)
    return cls(x, y, **kwargs)


def get_scaled_copy(obj):
    s = obj.sprite.copy()
    if obj.image_xscale < 0:
        s.mirror()
    if obj.image_yscale < 0:
        s.flip()
    s.width *= abs(obj.image_xscale)
    s.height *= abs(obj.image_yscale)
    s.rotate(obj.image_rotation)
    s.origin_x = obj.image_origin_x
    s.origin_y = obj.image_origin_y
    return s


def get_jump_speed(height, gravity=GRAVITY):
    # Get the speed to achieve a given height using a kinematic
    # equation: v[f]^2 = v[i]^2 + 2ad
    return -math.sqrt(2 * gravity * height)


def set_gui_controls():
    # Set the controls for xsge_gui based on the player controls.
    xsge_gui.next_widget_keys = (
        list(itertools.chain.from_iterable(down_key)) +
        list(itertools.chain.from_iterable(sneak_key)))
    if not xsge_gui.next_widget_keys:
        xsge_gui.next_widget_keys = ["tab"]
    xsge_gui.previous_widget_keys = list(itertools.chain.from_iterable(up_key))
    xsge_gui.left_keys = list(itertools.chain.from_iterable(left_key))
    xsge_gui.right_keys = list(itertools.chain.from_iterable(right_key))
    xsge_gui.up_keys = list(itertools.chain.from_iterable(up_key))
    xsge_gui.down_keys = list(itertools.chain.from_iterable(down_key))
    xsge_gui.enter_keys = (list(itertools.chain.from_iterable(jump_key)) +
                           list(itertools.chain.from_iterable(shoot_key)) +
                           list(itertools.chain.from_iterable(pause_key)))
    if not xsge_gui.enter_keys:
        xsge_gui.enter_keys = ["enter"]
    xsge_gui.escape_keys = (list(itertools.chain.from_iterable(mode_key)) +
                            ["escape"])
    xsge_gui.next_widget_joystick_events = (
        list(itertools.chain.from_iterable(down_js)) +
        list(itertools.chain.from_iterable(sneak_js)))
    if not xsge_gui.next_widget_joystick_events:
        xsge_gui.next_widget_joystick_events = [(0, "axis+", 1)]
    xsge_gui.previous_widget_joystick_events = (
        list(itertools.chain.from_iterable(up_js)))
    xsge_gui.left_joystick_events = list(itertools.chain.from_iterable(left_js))
    xsge_gui.right_joystick_events = (
        list(itertools.chain.from_iterable(right_js)))
    xsge_gui.up_joystick_events = list(itertools.chain.from_iterable(up_js))
    xsge_gui.down_joystick_events = list(itertools.chain.from_iterable(down_js))
    xsge_gui.enter_joystick_events = (
        list(itertools.chain.from_iterable(jump_js)) +
        list(itertools.chain.from_iterable(shoot_js)) +
        list(itertools.chain.from_iterable(pause_js)))
    if not xsge_gui.enter_joystick_events:
        xsge_gui.enter_joystick_events = [(0, "button", 9)]
    xsge_gui.escape_joystick_events = (
        list(itertools.chain.from_iterable(mode_js)))
    if not xsge_gui.escape_joystick_events:
        xsge_gui.escape_joystick_events = [(0, "button", 8)]


def wait_key():
    # Wait for a key press and return it.
    while True:
        # Input events
        sge.game.pump_input()
        while sge.game.input_events:
            event = sge.game.input_events.pop(0)
            if isinstance(event, sge.input.KeyPress):
                sge.game.pump_input()
                sge.game.input_events = []
                if event.key == "escape":
                    return None
                else:
                    return event.key

        # Regulate speed
        sge.game.regulate_speed(fps=10)

        # Project text
        text = _("Press the key you wish to toggle, or Escape to cancel.")
        sge.game.project_text(font, text, sge.game.width / 2,
                              sge.game.height / 2, width=sge.game.width,
                              height=sge.game.height,
                              color=sge.gfx.Color("white"),
                              halign="center", valign="middle")

        # Refresh
        sge.game.refresh()


def wait_js():
    # Wait for a joystick press and return it.
    sge.game.pump_input()
    sge.game.input_events = []

    while True:
        # Input events
        sge.game.pump_input()
        while sge.game.input_events:
            event = sge.game.input_events.pop(0)
            if isinstance(event, sge.input.KeyPress):
                if event.key == "escape":
                    sge.game.pump_input()
                    sge.game.input_events = []
                    return None
            elif isinstance(event, sge.input.JoystickEvent):
                if (event.input_type not in {"axis0", "hat_center_x",
                                             "hat_center_y"} and
                        event.value >= joystick_threshold):
                    sge.game.pump_input()
                    sge.game.input_events = []
                    return (event.js_id, event.input_type, event.input_id)

        # Regulate speed
        sge.game.regulate_speed(fps=10)

        # Project text
        text = _("Press the joystick button, axis, or hat direction you wish to toggle, or the Escape key to cancel.")
        sge.game.project_text(font, text, sge.game.width / 2,
                              sge.game.height / 2, width=sge.game.width,
                              height=sge.game.height,
                              color=sge.gfx.Color("white"),
                              halign="center", valign="middle")

        # Refresh
        sge.game.refresh()


def show_error(message):
    if sge.game.current_room is not None:
        sge.game.pump_input()
        sge.game.input_events = []
        sge.game.mouse.visible = True
        xsge_gui.show_message(message=message, title="Error", buttons=["Ok"],
                              width=640)
        sge.game.mouse.visible = False
    else:
        print(message)


def play_sound(sound, x=None, y=None):
    if sound_enabled and sound:
        if x is None or y is None:
            sound.play()
        else:
            current_view = None
            view_x = 0
            view_y = 0
            dist = 0
            for view in sge.game.current_room.views:
                vx = view.x + view.width / 2
                vy = view.y + view.height / 2
                new_dist = math.hypot(vx - x, vy - y)
                if current_view is None or new_dist < dist:
                    current_view = view
                    view_x = vx
                    view_y = vy
                    dist = new_dist

            bl = min(x, view_x)
            bw = abs(x - view_x)
            bt = min(y, view_y)
            bh = abs(y - view_y)
            for obj in sge.game.current_room.get_objects_at(bl, bt, bw, bh):
                if isinstance(obj, Player):
                    new_dist = math.hypot(obj.x - x, obj.y - y)
                    if new_dist < dist:
                        view_x = obj.x
                        view_y = obj.y
                        dist = new_dist

            if dist <= SOUND_MAX_RADIUS:
                volume = 1
            elif dist < SOUND_ZERO_RADIUS:
                rng = SOUND_ZERO_RADIUS - SOUND_MAX_RADIUS
                reldist = rng - (dist - SOUND_MAX_RADIUS)
                volume = min(1, abs(reldist / rng))
            else:
                # No point in continuing; it's too far away
                return

            if stereo_enabled:
                hdist = x - view_x
                if abs(hdist) < SOUND_CENTERED_RADIUS:
                    balance = 0
                else:
                    rng = SOUND_TILTED_RADIUS - SOUND_CENTERED_RADIUS
                    balance = max(-SOUND_TILT_LIMIT,
                                  min(hdist / rng, SOUND_TILT_LIMIT))
            else:
                balance = 0

            sound.play(volume=volume, balance=balance)


def play_music(music, force_restart=False):
    """Play the given music file, starting with its start piece."""
    if music_enabled and music:
        music_object = loaded_music.get(music)
        if music_object is None:
            try:
                music_object = sge.snd.Music(os.path.join(DATA, "music",
                                                          music))
            except IOError:
                sge.snd.Music.clear_queue()
                sge.snd.Music.stop()
                return
            else:
                loaded_music[music] = music_object

        name, ext = os.path.splitext(music)
        music_start = ''.join([name, "-start", ext])
        music_start_object = loaded_music.get(music_start)
        if music_start_object is None:
            try:
                music_start_object = sge.snd.Music(os.path.join(DATA, "music",
                                                                music_start))
            except IOError:
                pass
            else:
                loaded_music[music_start] = music_start_object

        if (force_restart or (not music_object.playing and
                              (music_start_object is None or
                               not music_start_object.playing))):
            sge.snd.Music.clear_queue()
            sge.snd.Music.stop()
            if music_start_object is not None:
                music_start_object.play()
                music_object.queue(loops=None)
            else:
                music_object.play(loops=None)
    else:
        sge.snd.Music.clear_queue()
        sge.snd.Music.stop()


def load_levelset(fname, preload_start=0):
    global current_levelset
    global start_cutscene
    global worldmap
    global loaded_worldmaps
    global levels
    global loaded_levels
    global tuxdolls_available
    global main_area

    def do_refresh():
        # Refresh the screen, return whether the user pressed a key.
        sge.game.pump_input()
        r = False
        while sge.game.input_events:
            event = sge.game.input_events.pop(0)
            if isinstance(event, sge.input.QuitRequest):
                sge.game.end()
                r = True
            elif isinstance(event, (sge.input.KeyPress,
                                    sge.input.JoystickButtonPress)):
                r = True

        gui_handler.event_step(0, 0)
        sge.game.refresh()
        return r

    if current_levelset != fname:
        current_levelset = fname

        with open(os.path.join(DATA, "levelsets", fname), 'r') as f:
            data = json.load(f)

        start_cutscene = data.get("start_cutscene")
        worldmap = data.get("worldmap")
        levels = data.get("levels", [])
        tuxdolls_available = data.get("tuxdolls_available", [])

        main_area = None

        w = 400
        h = 128
        margin = 16
        x = SCREEN_SIZE[0] / 2 - w / 2
        y = SCREEN_SIZE[1] / 2 - h / 2
        c = sge.gfx.Color("black")
        window = xsge_gui.Window(gui_handler, x, y, w, h,
                                 background_color=c, border=False)

        x = margin
        y = margin
        text = _("Preloading levels...\n\n(press any key to skip)")
        c = sge.gfx.Color("white")
        xsge_gui.Label(
            window, x, y, 1, text, font=font, width=(w - 2 * margin),
            height=(h - 3 * margin -
                    xsge_gui.progressbar_container_sprite.height), color=c)

        x = margin
        y = h - margin - xsge_gui.progressbar_container_sprite.height
        progressbar = xsge_gui.ProgressBar(window, x, y, 0,
                                           width=(w - 2 * margin))

        window.show()
        gui_handler.event_step(0, 0)
        sge.game.refresh()

        sorted_levels = levels[preload_start:] + levels[:preload_start]
        for level in sorted_levels:
            subrooms = [level]
            already_checked = []
            done = False

            while subrooms:
                subroom = subrooms.pop(0)
                already_checked.append(subroom)
                r = Level.load(subroom)
                if r is not None:
                    loaded_levels[subroom] = r
                    for obj in r.objects:
                        if isinstance(obj, (Door, Warp)):
                            if obj.dest and ':' in obj.dest:
                                map_f = obj.dest.split(':', 1)[0]
                                if (map_f not in subrooms and
                                        map_f not in already_checked and
                                        map_f not in {"__main__", "__map__"}):
                                    subrooms.append(map_f)
                if do_refresh():
                    done = True
                    break
            else:
                progressbar.progress = ((sorted_levels.index(level) + 1) /
                                        len(sorted_levels))
                progressbar.redraw()

            if done or do_refresh():
                break

        window.destroy()
        do_refresh()
        sge.game.pump_input()
        sge.game.input_events = []


def set_new_game():
    global level_timers
    global cleared_levels
    global tuxdolls_found
    global watched_timelines
    global current_worldmap
    global current_worldmap_space
    global current_level
    global score

    if current_levelset is None:
        load_levelset(DEFAULT_LEVELSET)

    level_timers = {}
    cleared_levels = []
    tuxdolls_found = []
    watched_timelines = []
    current_worldmap = worldmap
    current_worldmap_space = None
    current_level = None
    score = 0


def write_to_disk():
    # Write our saves and settings to disk.
    keys_cfg = {"left": left_key, "right": right_key, "up": up_key,
                "down": down_key, "halt": halt_key, "jump": jump_key,
                "shoot": shoot_key, "aim_up": aim_up_key,
                "aim_down": aim_down_key, "mode_reset": mode_reset_key,
                "mode": mode_key, "pause": pause_key}
    js_cfg = {"left": left_js, "right": right_js, "up": up_js,
              "down": down_js, "halt": halt_js, "jump": jump_js,
              "shoot": shoot_js, "aim_up": aim_up_js, "aim_down": aim_down_js,
              "mode_reset": mode_reset_js, "mode": mode_js, "pause": pause_js}

    cfg = {"version": 1, "fullscreen": fullscreen,
           "scale_method": scale_method, "sound_enabled": sound_enabled,
           "music_enabled": music_enabled, "stereo_enabled": stereo_enabled,
           "fps_enabled": fps_enabled,
           "joystick_threshold": joystick_threshold, "keys": keys_cfg,
           "joystick": js_cfg}

    with open(os.path.join(CONFIG, "config.json"), 'w') as f:
        json.dump(cfg, f, indent=4)

    with open(os.path.join(CONFIG, "save_slots.json"), 'w') as f:
        json.dump(save_slots, f, indent=4)


def save_game():
    global save_slots

    if current_save_slot is not None:
        if levels:
            completion = int(100 * (len(cleared_levels) + len(tuxdolls_found)) /
                             (len(levels) + len(tuxdolls_available)))
            if completion == 0 and (cleared_levels or tuxdolls_found):
                completion = 1
            elif (completion == 100 and
                  (len(cleared_levels) < len(levels) or
                   len(tuxdolls_found) < len(tuxdolls_available))):
                completion = 99
        else:
            completion = 100

        save_slots[current_save_slot] = {
            "levelset": current_levelset, "level_timers": level_timers,
            "cleared_levels": cleared_levels, "tuxdolls_found": tuxdolls_found,
            "watched_timelines": watched_timelines,
            "current_worldmap": current_worldmap,
            "current_worldmap_space": current_worldmap_space,
            "worldmap_entry_space": worldmap_entry_space,
            "current_level": current_level,
            "current_checkpoints": current_checkpoints, "score": score,
            "completion": completion}

    write_to_disk()


def load_game():
    global level_timers
    global cleared_levels
    global tuxdolls_found
    global watched_timelines
    global current_worldmap
    global current_worldmap_space
    global worldmap_entry_space
    global current_level
    global current_checkpoints
    global score

    if (current_save_slot is not None and
            save_slots[current_save_slot] is not None and
            save_slots[current_save_slot].get("levelset") is not None):
        slot = save_slots[current_save_slot]
        level_timers = slot.get("level_timers", {})
        cleared_levels = slot.get("cleared_levels", [])
        tuxdolls_found = slot.get("tuxdolls_found", [])
        watched_timelines = slot.get("watched_timelines", [])
        current_worldmap = slot.get("current_worldmap")
        current_worldmap_space = slot.get("current_worldmap_space")
        worldmap_entry_space = slot.get("worldmap_entry_space")
        current_level = slot.get("current_level", 0)
        current_checkpoints = slot.get("current_checkpoints", {})
        score = slot.get("score", 0)
        load_levelset(slot["levelset"], current_level)
    else:
        set_new_game()


def rush_save():
    global level_timers
    global cleared_levels
    global score
    global main_area

    if main_area is not None:
        if not cleared_levels and current_checkpoints.get(main_area) is None:
            level_timers[main_area] = level_time_bonus

        won = (isinstance(sge.game.current_room, Level) and
               sge.game.current_room.won)

        if won:
            score += sge.game.current_room.points
            sge.game.current_room.points = 0
            if main_area not in cleared_levels:
                cleared_levels.append(main_area)

        if won or level_timers.setdefault(main_area, 0) < 0:
            score += level_timers[main_area]
            level_timers[main_area] = 0

    save_game()
    main_area = None


def start_levelset():
    global current_level
    global main_area
    global level_cleared
    global current_areas
    current_areas = {}
    main_area = None
    level_cleared = True

    if start_cutscene and current_level is None:
        current_level = 0
        level = Level.load(start_cutscene, True)
        if level is not None:
            level.start()
        else:
            return False
    elif current_worldmap:
        m = Worldmap.load(current_worldmap)
        m.start()
    else:
        if current_level is None:
            current_level = 0

        if current_level < len(levels):
            level = Level.load(levels[current_level], True)
            if level is not None:
                level.start()
            else:
                return False
        else:
            print("Invalid save file: current level does not exist.")
            return False

    return True


def warp(dest):
    if dest == "__map__":
        sge.game.current_room.return_to_map(True)
    else:
        cr = sge.game.current_room

        if ":" in dest:
            level_f, spawn = dest.split(':', 1)
        else:
            level_f = None
            spawn = dest

        if level_f == "__main__":
            level_f = main_area

        if level_f:
            level = sge.game.current_room.__class__.load(level_f, True)
        else:
            level = cr

        if level is not None:
            level.spawn = spawn
            level.points = cr.points

            for nobj in level.objects[:]:
                if isinstance(nobj, Player):
                    for cobj in cr.objects[:]:
                        if (isinstance(cobj, Player) and
                                cobj.player == nobj.player):
                            nobj.hp = cobj.hp
                            nobj.coins = cobj.coins
                            nobj.facing = cobj.facing
                            nobj.image_xscale = cobj.image_xscale
                            nobj.image_yscale = cobj.image_yscale

                            held_object = cobj.held_object
                            if held_object is not None:
                                cobj.drop_object()
                                cr.remove(held_object)
                                level.add(held_object)
                                nobj.pickup(held_object)

                            break

            level.start()
        else:
            # Error occurred; restart the game.
            rush_save()
            sge.game.start_room.start()


TYPES = {"solid_left": SolidLeft, "solid_right": SolidRight,
         "solid_top": SolidTop, "solid_bottom": SolidBottom, "solid": Solid,
         "slope_topleft": SlopeTopLeft, "slope_topright": SlopeTopRight,
         "slope_bottomleft": SlopeBottomLeft,
         "slope_bottomright": SlopeBottomRight,
         "moving_platform": MovingPlatform, "spike_left": SpikeLeft,
         "spike_right": SpikeRight, "spike_top": SpikeTop,
         "spike_bottom": SpikeBottom, "death": Death, "level_end": LevelEnd,
         "creatures": get_object, "hazards": get_object,
         "special_blocks": get_object, "decoration_small": get_object,
         "map_objects": get_object, "player": Player,
         "walking_snowball": WalkingSnowball,
         "bouncing_snowball": BouncingSnowball,
         "walking_iceblock": WalkingIceblock, "spiky": Spiky,
         "bomb": WalkingBomb, "jumpy": Jumpy,
         "flying_snowball": FlyingSnowball, "flying_spiky": FlyingSpiky,
         "icicle": Icicle, "steady_icicle": SteadyIcicle,
         "raccot_icicle": RaccotIcicle, "krush": Krush, "krosh": Krosh,
         "circoflame": CircoflamePath, "circoflamecenter": CircoflameCenter,
         "snowman": Snowman, "raccot": Raccot, "fireflower": FireFlower,
         "iceflower": IceFlower, "tuxdoll": TuxDoll, "rock": Rock,
         "fixed_spring": FixedSpring, "spring": Spring,
         "rusty_spring": RustySpring, "lantern": Lantern,
         "timeline_switcher": TimelineSwitcher, "iceblock": Iceblock,
         "boss_block": BossBlock, "brick": Brick, "coinbrick": CoinBrick,
         "emptyblock": EmptyBlock, "itemblock": ItemBlock,
         "hiddenblock": HiddenItemBlock, "infoblock": InfoBlock,
         "thin_ice": ThinIce, "lava": Lava, "lava_surface": LavaSurface,
         "goal": Goal, "goal_top": GoalTop, "coin": Coin, "warp": Warp,
         "moving_platform_path": MovingPlatformPath,
         "triggered_moving_platform_path": TriggeredMovingPlatformPath,
         "flying_snowball_path": FlyingSnowballPath,
         "flying_spiky_path": FlyingSpikyPath, "spawn": Spawn,
         "checkpoint": Checkpoint, "bell": Bell, "door": Door,
         "warp_spawn": WarpSpawn, "object_warp_spawn": ObjectWarpSpawn,
         "map_player": MapPlayer, "map_level": MapSpace, "map_warp": MapWarp,
         "map_path": MapPath, "map_water": MapWater}


print(_("Initializing game system..."))
Game(SCREEN_SIZE[0], SCREEN_SIZE[1], fps=FPS, delta=DELTA, delta_min=DELTA_MIN,
     delta_max=DELTA_MAX, window_text="Hexoshi {}".format(__version__),
     window_icon=os.path.join(DATA, "images", "misc", "icon.png"))

print(_("Initializing GUI system..."))
xsge_gui.init()
gui_handler = xsge_gui.Handler()

menu_color = sge.gfx.Color((128, 128, 255, 192))

# Load sprites
print(_("Loading images..."))

d = os.path.join(DATA, "images", "objects", "anneroy")

fname = os.path.join(d, "anneroy_sheet.png")
anneroy_torso_right_idle_sprite = sge.gfx.Sprite.from_tileset(
    fname, 317, 45, width=26, height=27, origin_x=9, origin_y=19)
anneroy_torso_right_aim_right = sge.gfx.Sprite.from_tileset(
    fname, 234, 45, width=26, height=20, origin_x=4, origin_y=19)
anneroy_torso_right_aim_up = sge.gfx.Sprite.from_tileset(
    fname, 293, 38, width=20, height=27, origin_x=5, origin_y=26)
anneroy_torso_right_aim_down = sge.gfx.Sprite.from_tileset(
    fname, 182, 52, width=20, height=30, origin_x=0, origin_y=12)
anneroy_torso_right_aim_upright = sge.gfx.Sprite.from_tileset(
    fname, 264, 39, width=25, height=26, origin_x=4, origin_y=25)
anneroy_torso_right_aim_downright = sge.gfx.Sprite.from_tileset(
    fname, 207, 45, width=23, height=26, origin_x=4, origin_y=19)

anneroy_legs_stand_sprite = sge.gfx.Sprite.from_tileset(
    fname, 45, 76, width=21, height=24, origin_x=8, origin_y=0)

d = os.path.join(DATA, "images", "portraits")
portrait_sprites = {}
for fname in os.listdir(d):
    root, ext = os.path.splitext(fname)
    try:
        portrait = sge.gfx.Sprite(root, d)
    except IOError:
        pass
    else:
        portrait_sprites[root] = portrait

# Load backgrounds
d = os.path.join(DATA, "images", "backgrounds")
layers = []

if not NO_BACKGROUNDS:
    layers = [
        sge.gfx.BackgroundLayer(
            sge.gfx.Sprite("arctis1-middle", d), 0, 0, -100000,
            xscroll_rate=0.5, yscroll_rate=0.5, repeat_left=True,
            repeat_right=True),
        sge.gfx.BackgroundLayer(
            sge.gfx.Sprite("arctis1-bottom", d, transparent=False), 0, 352,
            -100000, xscroll_rate=0.5, yscroll_rate=0.5, repeat_left=True,
            repeat_right=True, repeat_down=True),
        sge.gfx.BackgroundLayer(
            sge.gfx.Sprite("arctis2-middle", d), 0, 0, -100010,
            xscroll_rate=0.25, yscroll_rate=0.25, repeat_left=True,
            repeat_right=True),
        sge.gfx.BackgroundLayer(
            sge.gfx.Sprite("arctis2-bottom", d, transparent=False), 0, 352,
            -100010, xscroll_rate=0.25, yscroll_rate=0.25, repeat_left=True,
            repeat_right=True, repeat_down=True),
        sge.gfx.BackgroundLayer(
            sge.gfx.Sprite("arctis3", d, transparent=False), 0, 0, -100020,
            xscroll_rate=0, yscroll_rate=0.25, repeat_left=True,
            repeat_right=True)]

backgrounds["arctis"] = sge.gfx.Background(layers,
                                           sge.gfx.Color((109, 92, 230)))

if not NO_BACKGROUNDS:
    cave_edge_spr = sge.gfx.Sprite("cave-edge", d, transparent=False)
    layers = [
        sge.gfx.BackgroundLayer(
            sge.gfx.Sprite("cave-middle", d, transparent=False), 0, 128,
            -100000, xscroll_rate=0.7, yscroll_rate=0.7, repeat_left=True,
            repeat_right=True),
        sge.gfx.BackgroundLayer(
            cave_edge_spr, 0, 0, -100000, xscroll_rate=0.7, yscroll_rate=0.7,
            repeat_left=True, repeat_right=True, repeat_up=True),
        sge.gfx.BackgroundLayer(
            cave_edge_spr, 0, 256, -100000, xscroll_rate=0.7, yscroll_rate=0.7,
            repeat_left=True, repeat_right=True, repeat_down=True)]
    del cave_edge_spr

backgrounds["cave"] = sge.gfx.Background(layers, sge.gfx.Color("#024"))

if not NO_BACKGROUNDS:
    nightsky_bottom_spr = sge.gfx.Sprite("nightsky-bottom", d,
                                         transparent=False)
    layers = [
        sge.gfx.BackgroundLayer(
            sge.gfx.Sprite("nightsky1-middle", d), 0, 306, -100000,
            xscroll_rate=0.5, yscroll_rate=0.5, repeat_left=True,
            repeat_right=True),
        sge.gfx.BackgroundLayer(
            nightsky_bottom_spr, 0, 664, -100000, xscroll_rate=0.5,
            yscroll_rate=0.5, repeat_left=True, repeat_right=True,
            repeat_down=True),
        sge.gfx.BackgroundLayer(
            sge.gfx.Sprite("nightsky2-middle", d, transparent=False), 0, 0,
            -100010, xscroll_rate=0.25, yscroll_rate=0.25, repeat_left=True,
            repeat_right=True),
        sge.gfx.BackgroundLayer(
            sge.gfx.Sprite("nightsky2-top", d, transparent=False), 0, -600,
            -100010, xscroll_rate=0.25, yscroll_rate=0.25, repeat_left=True,
            repeat_right=True, repeat_up=True),
        sge.gfx.BackgroundLayer(
            nightsky_bottom_spr, 0, 600, -100010, xscroll_rate=0.25,
            yscroll_rate=0.25, repeat_left=True, repeat_right=True,
            repeat_down=True)]
    del nightsky_bottom_spr

backgrounds["nightsky"] = sge.gfx.Background(layers, sge.gfx.Color("#002"))

if not NO_BACKGROUNDS:
    layers = [
        sge.gfx.BackgroundLayer(
            sge.gfx.Sprite("bluemountain-middle", d, transparent=False), 0,
            -128, -100000, xscroll_rate=0.1, yscroll_rate=0.1,
            repeat_left=True, repeat_right=True),
        sge.gfx.BackgroundLayer(
            sge.gfx.Sprite("bluemountain-top", d, transparent=False), 0, -704,
            -100000, xscroll_rate=0.1, yscroll_rate=0.1, repeat_left=True,
            repeat_right=True, repeat_up=True),
        sge.gfx.BackgroundLayer(
            sge.gfx.Sprite("bluemountain-bottom", d, transparent=False), 0,
            448, -100000, xscroll_rate=0.1, yscroll_rate=0.1, repeat_left=True,
            repeat_right=True, repeat_down=True)]

backgrounds["bluemountain"] = sge.gfx.Background(layers,
                                                 sge.gfx.Color((86, 142, 206)))

castle_spr = sge.gfx.Sprite("castle", d)
castle_bottom_spr = sge.gfx.Sprite("castle-bottom", d, transparent=False)
for i in list(backgrounds.keys()):
    if not NO_BACKGROUNDS:
        layers = backgrounds[i].layers + [
            sge.gfx.BackgroundLayer(castle_spr, 0, -64, -99000,
                                    xscroll_rate=0.75, yscroll_rate=1,
                                    repeat_left=True, repeat_right=True,
                                    repeat_up=True),
            sge.gfx.BackgroundLayer(castle_bottom_spr, 0, 544, -99000,
                                    xscroll_rate=0.75, yscroll_rate=1,
                                    repeat_left=True, repeat_right=True,
                                    repeat_down=True)]

        backgrounds["{}_castle".format(i)] = sge.gfx.Background(
            layers, backgrounds[i].color)
    else:
        backgrounds["{}_castle".format(i)] = sge.gfx.Background(
            [], sge.gfx.Color("#221833"))
del castle_spr
del castle_bottom_spr

# Load fonts
print(_("Loading fonts..."))
chars = (['\x00'] + [six.unichr(i) for i in six.moves.range(33, 128)] +
         [six.unichr(i) for i in six.moves.range(160, 384)])

font_sprite = sge.gfx.Sprite.from_tileset(
    os.path.join(DATA, "images", "misc", "font.png"), columns=16, rows=20,
    width=16, height=18)
font = sge.gfx.Font.from_sprite(font_sprite, chars, size=18)

font_small_sprite = sge.gfx.Sprite.from_tileset(
    os.path.join(DATA, "images", "misc", "font_small.png"), columns=16,
    rows=20, width=8, height=9)
font_small = sge.gfx.Font.from_sprite(font_small_sprite, chars, size=9)

font_big_sprite = sge.gfx.Sprite.from_tileset(
    os.path.join(DATA, "images", "misc", "font_big.png"), columns=16, rows=20,
    width=20, height=22)
font_big = sge.gfx.Font.from_sprite(font_big_sprite, chars, size=22)

# Load sounds
jump_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "jump.wav"))
bigjump_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "bigjump.wav"))
skid_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "skid.wav"), 50)
hurt_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "hurt.wav"))
kill_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "kill.wav"))
brick_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "brick.wav"))
coin_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "coin.wav"))
find_powerup_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "upgrade.wav"))
tuxdoll_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "tuxdoll.wav"))
ice_crack_sounds = [
    sge.snd.Sound(os.path.join(DATA, "sounds", "ice_crack-0.wav")),
    sge.snd.Sound(os.path.join(DATA, "sounds", "ice_crack-1.wav")),
    sge.snd.Sound(os.path.join(DATA, "sounds", "ice_crack-2.wav")),
    sge.snd.Sound(os.path.join(DATA, "sounds", "ice_crack-3.wav"))]
ice_shatter_sound = sge.snd.Sound(os.path.join(DATA, "sounds",
                                               "ice_shatter.wav"))
heal_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "heal.wav"))
shoot_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "shoot.wav"))
fire_dissipate_sound = sge.snd.Sound(os.path.join(DATA, "sounds",
                                                  "fire_dissipate.wav"))
icebullet_break_sound = sge.snd.Sound(os.path.join(DATA, "sounds",
                                                   "icebullet_break.wav"))
squish_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "squish.wav"))
stomp_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "stomp.wav"))
sizzle_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "sizzle.ogg"))
spring_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "spring.wav"))
rusty_spring_sound = sge.snd.Sound(os.path.join(DATA, "sounds",
                                                "rusty_spring.wav"))
kick_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "kick.wav"))
iceblock_bump_sound = sge.snd.Sound(os.path.join(DATA, "sounds",
                                                 "iceblock_bump.wav"))
icicle_shake_sound = sge.snd.Sound(os.path.join(DATA, "sounds",
                                                "icicle_shake.wav"))
icicle_crash_sound = sge.snd.Sound(os.path.join(DATA, "sounds",
                                                "icicle_crash.wav"))
explosion_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "explosion.wav"))
fall_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "fall.wav"))
yeti_gna_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "yeti_gna.wav"))
yeti_roar_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "yeti_roar.wav"))
pop_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "pop.wav"))
bell_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "bell.wav"))
pipe_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "pipe.ogg"))
warp_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "warp.wav"))
door_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "door.wav"))
door_shut_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "door_shut.wav"))
pause_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "select.ogg"))
select_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "select.ogg"))
confirm_sound = coin_sound
cancel_sound = pop_sound
error_sound = hurt_sound
type_sound = sge.snd.Sound(os.path.join(DATA, "sounds", "type.wav"))

# Load music
level_win_music = sge.snd.Music(os.path.join(DATA, "music", "leveldone.ogg"))
loaded_music["leveldone.ogg"] = level_win_music

# Create objects
coin_animation = sge.dsp.Object(0, 0, sprite=coin_sprite, visible=False,
                                tangible=False)
bonus_animation = sge.dsp.Object(0, 0, sprite=bonus_empty_sprite,
                                 visible=False, tangible=False)
lava_animation = sge.dsp.Object(0, 0, sprite=lava_body_sprite, visible=False,
                                tangible=False)
goal_animation = sge.dsp.Object(0, 0, sprite=goal_sprite, visible=False,
                                tangible=False)

# Create rooms
if LEVEL:
    sge.game.start_room = LevelTester.load(LEVEL, True)
    if sge.game.start_room is None:
        sys.exit()
elif RECORD:
    sge.game.start_room = LevelRecorder.load(RECORD, True)
    if sge.game.start_room is None:
        sys.exit()
else:
    sge.game.start_room = TitleScreen.load(
        os.path.join("special", "title_screen.tmx"), True)

sge.game.mouse.visible = False

if not os.path.exists(CONFIG):
    os.makedirs(CONFIG)

# Save error messages to a text file (so they aren't lost).
if not PRINT_ERRORS:
    stderr = os.path.join(CONFIG, "stderr.txt")
    if not os.path.isfile(stderr) or os.path.getsize(stderr) > 1000000:
        sys.stderr = open(stderr, 'w')
    else:
        sys.stderr = open(stderr, 'a')
    dt = datetime.datetime.now()
    sys.stderr.write("\n{}-{}-{} {}:{}:{}\n".format(
        dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second))
    del dt

try:
    with open(os.path.join(CONFIG, "config.json")) as f:
        cfg = json.load(f)
except (IOError, ValueError):
    cfg = {}
finally:
    cfg_version = cfg.get("version", 0)

    fullscreen = cfg.get("fullscreen", fullscreen)
    sge.game.fullscreen = fullscreen
    scale_method = cfg.get("scale_method", scale_method)
    sge.game.scale_method = scale_method
    sound_enabled = cfg.get("sound_enabled", sound_enabled)
    music_enabled = cfg.get("music_enabled", music_enabled)
    stereo_enabled = cfg.get("stereo_enabled", stereo_enabled)
    fps_enabled = cfg.get("fps_enabled", fps_enabled)
    joystick_threshold = cfg.get("joystick_threshold", joystick_threshold)
    xsge_gui.joystick_threshold = joystick_threshold

    keys_cfg = cfg.get("keys", {})
    left_key = keys_cfg.get("left", left_key)
    right_key = keys_cfg.get("right", right_key)
    up_key = keys_cfg.get("up", up_key)
    halt_key = keys_cfg.get("halt", halt_key)
    down_key = keys_cfg.get("down", down_key)
    jump_key = keys_cfg.get("jump", jump_key)
    shoot_key = keys_cfg.get("shoot", shoot_key)
    aim_up_key = keys_cfg.get("aim_up", aim_up_key)
    aim_down_key = keys_cfg.get("aim_down", aim_down_key)
    mode_reset_key = keys_cfg.get("mode_reset", mode_reset_key)
    mode_key = keys_cfg.get("mode", mode_key)
    pause_key = keys_cfg.get("pause", pause_key)

    js_cfg = cfg.get("joystick", {})
    left_js = [[tuple(j) for j in js] for js in js_cfg.get("left", left_js)]
    right_js = [[tuple(j) for j in js] for js in js_cfg.get("right", right_js)]
    up_js = [[tuple(j) for j in js] for js in js_cfg.get("up", up_js)]
    down_js = [[tuple(j) for j in js] for js in js_cfg.get("down", down_js)]
    halt_js = [[tuple(j) for j in js] for js in js_cfg.get("halt", halt_js)]
    jump_js = [[tuple(j) for j in js] for js in js_cfg.get("jump", jump_js)]
    shoot_js = [[tuple(j) for j in js] for js in js_cfg.get("shoot", shoot_js)]
    aim_up_js = [[tuple(j) for j in js]
                 for js in js_cfg.get("aim_up", aim_up_js)]
    aim_down_js = [[tuple(j) for j in js]
                   for js in js_cfg.get("aim_down", aim_down_js)]
    mode_reset_js = [[tuple(j) for j in js]
                     for js in js_cfg.get("mode_reset", mode_reset_js)]
    mode_js = [[tuple(j) for j in js] for js in js_cfg.get("mode", mode_js)]
    pause_js = [[tuple(j) for j in js] for js in js_cfg.get("pause", pause_js)]

    set_gui_controls()

try:
    with open(os.path.join(CONFIG, "save_slots.json")) as f:
        loaded_slots = json.load(f)
except (IOError, ValueError):
    pass
else:
    for i in six.moves.range(min(len(loaded_slots), len(save_slots))):
        save_slots[i] = loaded_slots[i]


if __name__ == '__main__':
    print(_("Starting game..."))

    if HAVE_TK:
        tkwindow = Tk()
        tkwindow.withdraw()

    try:
        sge.game.start()
    finally:
        write_to_disk()
        shutil.rmtree(DATA)
