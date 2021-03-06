from BTData import *
import pandas as pd
import numpy as np
import os
import csv
import glob
import json
import matplotlib.pyplot as plt
import random
import scipy
from scipy import stats, signal
from itertools import groupby
import MountainViewIO
from scipy.ndimage.filters import gaussian_filter
from datetime import datetime
# import InterruptionAnalysis

INSPECT_ALL = False
INSPECT_IN_DETAIL = []
# INSPECT_IN_DETAIL = ["20200526"]
INSPECT_NANVALS = False
INSPECT_PROBE_BEHAVIOR_PLOT = False
INSPECT_PLOT_WELL_OCCUPANCIES = False
ENFORCE_DIFFERENT_WELL_COLORS = False
RUN_JUST_SPECIFIED = False
SPECIFIED_DAYS = ["20200604"]
INSPECT_BOUTS = True
SAVE_DONT_SHOW = True
SHOW_CURVATURE_VIDEO = False

TEST_NEAREST_WELL = False

animal_name = 'Martin'

if animal_name == "Martin":
    data_dir = '/media/WDC1/martindata/bradtask/'
    output_dir = '/media/WDC1/martindata/bradtask/'
    fig_output_dir = '/media/WDC1/martindata/processed_data'
    out_filename = "martin_bradtask.dat"

    excluded_dates = ["20200528", "20200630", "20200702", "20200703"]
    excluded_dates += ["20200531",  "20200603", "20200602",
                       "20200606", "20200605", "20200601"]
    excluded_dates += ["20200526"]
    excluded_sessions = ["20200624_1", "20200624_2", "20200628_2"]

elif animal_name == "B12":
    data_dir = "/media/TOSHIBA EXT1/B12/bradtasksessions/"
    output_dir = "/media/TOSHIBA EXT1/B12/processed_data/"
    fig_output_dir = "/media/TOSHIBA EXT1/B12/processed_data/"
    out_filename = "B12_bradtask.dat"


all_data_dirs = sorted(os.listdir(data_dir), key=lambda s: (
    s.split('_')[0], s.split('_')[1]))
behavior_notes_dir = os.path.join(data_dir, 'behavior_notes')

if os.path.exists(os.path.join(output_dir, out_filename)):
    # confirm = input("Output file exists already. Overwrite? (y/n):")
    confirm = "y"
    if confirm != "y":
        exit()

all_well_names = np.array([i + 1 for i in range(48) if not i % 8 in [0, 7]])
all_quadrant_idxs = [0, 1, 2, 3]
well_name_to_idx = np.empty((np.max(all_well_names)+1))
well_name_to_idx[:] = np.nan
for widx, wname in enumerate(all_well_names):
    well_name_to_idx[wname] = widx


MAX_JUMP_DISTANCE = 50
N_CLEANING_REPS = 2
X_START = 200
X_FINISH = 1175
Y_START = 20
Y_FINISH = 1275
RADIUS = 50  # pixels
VEL_THRESH = 10  # cm/s
PIXELS_PER_CM = 5.0
TRODES_SAMPLING_RATE = 30000
# 0.8 means transition from well a -> b requires rat dist to b to be 0.8 * dist to a
SWITCH_WELL_FACTOR = 0.8

# Typical observed amplitude of LFP deflection on stimulation
DEFLECTION_THRESHOLD_HI = 10000.0
DEFLECTION_THRESHOLD_LO = 2000.0
LFP_SAMPLING_RATE = 1500.0
MIN_ARTIFACT_DISTANCE = int(0.05 * LFP_SAMPLING_RATE)

SAMPLING_RATE = 30000.0  # Rate at which timestamp data is sampled
# LFP is subsampled. The timestamps give time according to SAMPLING_RATE above
LFP_SAMPLING_RATE = 1500.0
# Typical duration of the stimulation artifact - For peak detection
MIN_ARTIFACT_PERIOD = int(0.1 * LFP_SAMPLING_RATE)
# Typical duration of a Sharp-Wave Ripple
ACCEPTED_RIPPLE_LENGTH = int(0.2 * LFP_SAMPLING_RATE)
RIPPLE_FILTER_BAND = [150, 250]
RIPPLE_FILTER_ORDER = 4
SKIP_TPTS_FORWARD = int(0.075 * LFP_SAMPLING_RATE)
# SKIP_TPTS_BACKWARD = int(0.005 * LFP_SAMPLING_RATE)
SKIP_TPTS_BACKWARD = int(0.02 * LFP_SAMPLING_RATE)

# constants for exploration bout analysis
# raise Exception("try longer sigmas here")
BOUT_VEL_SM_SIGMA_SECS = 1.5
PAUSE_MAX_SPEED_CM_S = 8.0
MIN_PAUSE_TIME_BETWEEN_BOUTS_SECS = 2.5
MIN_EXPLORE_TIME_SECS = 3.0
MIN_EXPLORE_NUM_WELLS = 4
# COUNT_ONE_WELL_VISIT_PER_BOUT = False

# constants for ballisticity
# BALL_TIME_INTERVALS = list(range(1, 12, 3))
BALL_TIME_INTERVALS = list(range(1, 24))
# KNOT_H_CM = 20.0
KNOT_H_CM = 8.0
KNOT_H_POS = KNOT_H_CM * PIXELS_PER_CM

DIST_TO_HOME_RESOLUTION = 30

# def readPositionData(data_filename):
#     trajectory_data = None
#     try:
#         with open(data_filename, 'r') as data_file:
#             timestamp_data = list()
#             x_data = list()
#             y_data = list()
#             csv_reader = csv.reader(data_file)
#             n_elements = 0
#             for data_row in csv_reader:
#                 if data_row:
#                     n_elements += 1
#                     timestamp_data.append(int(data_row[0]))
#                     x_data.append(int(data_row[1]))
#                     y_data.append(int(data_row[2]))
#             trajectory_data = np.empty((n_elements, 3), dtype=np.uint32)
#             trajectory_data[:, 0] = timestamp_data[:]
#             trajectory_data[:, 2] = x_data[:]
#             trajectory_data[:, 1] = y_data[:]
#     except Exception as err:
#         print(err)
#     return trajectory_data

# well_coords_file = '/home/wcroughan/repos/BradsTaskAnalysis/well_locations.csv'


def readWellCoordsFile(well_coords_file):
    # For some reason json saving and loading turns the keys into strings, just going to change that here so it's consistent
    with open(well_coords_file, 'r') as wcf:
        well_coords_map = {}
        csv_reader = csv.reader(wcf)
        for data_row in csv_reader:
            try:
                well_coords_map[str(int(data_row[0]))] = (
                    int(data_row[1]), int(data_row[2]))
            except Exception as err:
                if data_row[1] != '':
                    print(err)

        return well_coords_map


def readRawPositionData(data_filename):
    try:
        with open(data_filename, 'rb') as datafile:
            dt = np.dtype([('timestamp', np.uint32), ('x1', np.uint16),
                           ('y1', np.uint16), ('x2', np.uint16), ('y2', np.uint16)])
            l = ""
            max_iter = 8
            iter = 0
            while l != b'<end settings>\n':
                l = datafile.readline().lower()
                # print(l)
                iter += 1
                if iter > max_iter:
                    raise Exception
            return np.fromfile(datafile, dtype=dt)
    except Exception as err:
        print(err)
        return 0


def readClipData(data_filename):
    time_clips = None
    try:
        with open(data_filename, 'r') as data_file:
            start_times = list()
            finish_times = list()
            csv_reader = csv.reader(data_file)
            n_time_clips = 0
            for data_row in csv_reader:
                if data_row:
                    n_time_clips += 1
                    start_times.append(int(data_row[1]))
                    finish_times.append(int(data_row[2]))
            time_clips = np.empty((n_time_clips, 2), dtype=np.uint32)
            time_clips[:, 0] = start_times[:]
            time_clips[:, 1] = finish_times[:]
    except Exception as err:
        print(err)
    return time_clips


def processPosData(position_data):
    x_pos = np.array(position_data['x1'], dtype=float)
    y_pos = np.array(position_data['y1'], dtype=float)

    # Interpolate the position data into evenly sampled time points
    x = np.linspace(position_data['timestamp'][0],
                    position_data['timestamp'][-1], position_data.shape[0])
    xp = position_data['timestamp']
    x_pos = np.interp(x, xp, position_data['x1'])
    y_pos = np.interp(x, xp, position_data['y1'])
    position_sampling_frequency = TRODES_SAMPLING_RATE/np.diff(x)[0]
    # Interpolated Timestamps:
    position_data['timestamp'] = x

    # Remove large jumps in position (tracking errors)
    for _ in range(N_CLEANING_REPS):
        jump_distance = np.sqrt(np.square(np.diff(x_pos, prepend=x_pos[0])) +
                                np.square(np.diff(y_pos, prepend=y_pos[0])))
        # print(jump_distance)
        points_in_range = (x_pos > X_START) & (x_pos < X_FINISH) &\
            (y_pos > Y_START) & (y_pos < Y_FINISH)
        clean_points = jump_distance < MAX_JUMP_DISTANCE

    # substitute them with NaNs then interpolate
    x_pos[np.logical_not(clean_points & points_in_range)] = np.nan
    y_pos[np.logical_not(clean_points & points_in_range)] = np.nan

    # try:
    #     assert not np.isnan(x_pos[0])
    #     assert not np.isnan(y_pos[0])
    #     assert not np.isnan(x_pos[-1])
    #     assert not np.isnan(y_pos[-1])
    # except:
    #     nans = np.argwhere(np.isnan(x_pos))
    #     print("nans (", np.size(nans), "):", nans)
    #     exit()

    nanpos = np.isnan(x_pos)
    notnanpos = np.logical_not(nanpos)
    x_pos = np.interp(x, x[notnanpos], x_pos[notnanpos])
    y_pos = np.interp(x, x[notnanpos], y_pos[notnanpos])

    return list(x_pos), list(y_pos), list(x)


def get_well_coordinates(well_num, well_coords_map):
    return well_coords_map[str(well_num)]


def getMeanDistToWell(xs, ys, wellx, welly, duration=-1, ts=np.array([])):
    # Note nan values are ignored. This is intentional, so caller
    # can just consider some time points by making all other values nan
    # If duration == -1, use all times points. Otherwise, take only duration in seconds
    if duration != -1:
        assert xs.shape == ts.shape
        dur_idx = np.searchsorted(ts, ts[0] + duration)
        xs = xs[0:dur_idx]
        ys = ys[0:dur_idx]

    dist_to_well = np.sqrt(np.power(wellx - np.array(xs), 2) +
                           np.power(welly - np.array(ys), 2))
    return np.nanmean(dist_to_well)


def getMedianDistToWell(xs, ys, wellx, welly, duration=-1, ts=np.array([])):
    # Note nan values are ignored. This is intentional, so caller
    # can just consider some time points by making all other values nan
    # If duration == -1, use all times points. Otherwise, take only duration in seconds
    if duration != -1:
        assert xs.shape == ts.shape
        dur_idx = np.searchsorted(ts, ts[0] + duration)
        xs = xs[0:dur_idx]
        ys = ys[0:dur_idx]

    dist_to_well = np.sqrt(np.power(wellx - np.array(xs), 2) +
                           np.power(welly - np.array(ys), 2))
    return np.nanmedian(dist_to_well)


def getMeanDistToWells(xs, ys, well_coords, duration=-1, ts=np.array([])):
    res = []
    for wi in all_well_names:
        wx, wy = get_well_coordinates(wi, well_coords)
        res.append(getMeanDistToWell(np.array(xs), np.array(
            ys), wx, wy, duration=duration, ts=np.array(ts)))

    return res


def getMedianDistToWells(xs, ys, well_coords, duration=-1, ts=np.array([])):
    res = []
    for wi in all_well_names:
        wx, wy = get_well_coordinates(wi, well_coords)
        res.append(getMedianDistToWell(np.array(xs), np.array(
            ys), wx, wy, duration=duration, ts=np.array(ts)))

    return res


def getNearestWell(xs, ys, well_coords, well_idxs=all_well_names):
    well_coords = np.array(
        [get_well_coordinates(i, well_coords) for i in well_idxs])
    tiled_x = np.tile(xs, (len(well_idxs), 1)).T  # each row is one time point
    tiled_y = np.tile(ys, (len(well_idxs), 1)).T

    tiled_wells_x = np.tile(well_coords[:, 0], (len(xs), 1))
    tiled_wells_y = np.tile(well_coords[:, 1], (len(ys), 1))

    delta_x = tiled_wells_x - tiled_x
    delta_y = tiled_wells_y - tiled_y
    delta = np.sqrt(np.power(delta_x, 2) + np.power(delta_y, 2))

    raw_nearest_wells = np.argmin(delta, axis=1)
    nearest_well = raw_nearest_wells
    curr_well = nearest_well[0]
    for i in range(np.shape(xs)[0]):
        if curr_well != nearest_well[i]:
            if delta[i, nearest_well[i]] < SWITCH_WELL_FACTOR * delta[i, curr_well]:
                curr_well = nearest_well[i]
            else:
                nearest_well[i] = curr_well

    # if TEST_NEAREST_WELL:
    #     print("delta_x", delta_x)
    #     print("delta_y", delta_y)
    #     print("delta", delta)
    #     print("raw_nearest_wells", raw_nearest_wells)
    #     print("nearest_well", nearest_well)

    return well_idxs[nearest_well]


def get_ripple_power(lfp_data, omit_artifacts=True, causal_smoothing=False, lfp_deflections=None):
    """
    Get ripple power in LFP
    """

    lfp_data_copy = lfp_data.copy()

    if lfp_deflections is None:
        if omit_artifacts:
            raise Exception("this hasn't been updated")
            # Remove all the artifacts in the raw ripple amplitude data
            deflection_metrics = signal.find_peaks(np.abs(np.diff(lfp_data,
                                                                  prepend=lfp_data[0])), height=DEFLECTION_THRESHOLD_LO,
                                                   distance=MIN_ARTIFACT_DISTANCE)
            lfp_deflections = deflection_metrics[0]

    # After this preprocessing, clean up the data if needed.
    if lfp_deflections is not None:
        for artifact_idx in range(len(lfp_deflections)):
            cleanup_start = max(0, lfp_deflections[artifact_idx] - SKIP_TPTS_BACKWARD)
            cleanup_finish = min(len(lfp_data)-1, lfp_deflections[artifact_idx] +
                                 SKIP_TPTS_FORWARD)
            lfp_data_copy[cleanup_start:cleanup_finish] = np.nan

    nyq_freq = LFP_SAMPLING_RATE * 0.5
    lo_cutoff = RIPPLE_FILTER_BAND[0]/nyq_freq
    hi_cutoff = RIPPLE_FILTER_BAND[1]/nyq_freq
    pl, ph = signal.butter(RIPPLE_FILTER_ORDER, [lo_cutoff, hi_cutoff], btype='band')
    if causal_smoothing:
        ripple_amplitude = signal.lfilter(pl, ph, lfp_data_copy)
    else:
        ripple_amplitude = signal.filtfilt(pl, ph, lfp_data_copy)

    # Smooth this data and get ripple power
    # smoothing_window_length = RIPPLE_POWER_SMOOTHING_WINDOW * LFP_SAMPLING_RATE
    # smoothing_weights = np.ones(int(smoothing_window_length))/smoothing_window_length
    # ripple_power = np.convolve(np.abs(ripple_amplitude), smoothing_weights, mode='same')

    # Use a Gaussian kernel for filtering - Make the Kernel Causal bu keeping only one half of the values
    smoothing_window_length = 10
    if causal_smoothing:
        # In order to no have NaN values affect the filter output, create a copy with the artifacts
        ripple_amplitude_copy = ripple_amplitude.copy()

        half_smoothing_signal = \
            np.exp(-np.square(np.linspace(0, -4*smoothing_window_length, 4 *
                                          smoothing_window_length))/(2*smoothing_window_length * smoothing_window_length))
        smoothing_signal = np.concatenate(
            (np.zeros_like(half_smoothing_signal), half_smoothing_signal), axis=0)
        ripple_power = signal.convolve(np.abs(ripple_amplitude_copy),
                                       smoothing_signal, mode='same') / np.sum(smoothing_signal)
        ripple_power[np.isnan(ripple_amplitude)] = np.nan
    else:
        ripple_power = gaussian_filter(np.abs(ripple_amplitude), smoothing_window_length)

    # Get the mean/standard deviation for ripple power and adjust for those
    mean_ripple_power = np.nanmean(ripple_power)
    std_ripple_power = np.nanstd(ripple_power)
    return (ripple_power-mean_ripple_power)/std_ripple_power, lfp_deflections


if __name__ == "__main__" and TEST_NEAREST_WELL:
    raise Exception("Unimplemented")
    # w1 = 2
    # w2 = 3
    # numpts = 20
    # # numpts = 3
    # w1x, w1y = get_well_coordinates(w1)
    # w2x, w2y = get_well_coordinates(w2)
    # xs = np.linspace(w1x, w2x, numpts)
    # ys = np.linspace(w1y, w2y, numpts)
    # ws = getNearestWell(xs, ys)
    # print(xs)
    # print(ys)
    # print(ws)
    # plt.clf()
    # plt.scatter(xs, ys, c=ws)
    # plt.show()
    # exit()


def getWellEntryAndExitTimes(nearest_wells, ts, well_idxs=all_well_names, include_neighbors=False):
    entry_times = []
    exit_times = []
    entry_idxs = []
    exit_idxs = []

    ts = np.array(ts)
    for wi in well_idxs:
        # last data point should count as an exit, so appending a false
        # same for first point should count as entry, prepending
        if include_neighbors:
            neighbors = list({wi, wi-1, wi+1, wi-7, wi-8, wi-9,
                              wi+7, wi+8, wi+9}.intersection(all_well_names))
            near_well = np.concatenate(
                ([False], np.isin(nearest_wells, neighbors), [False]))
        else:
            near_well = np.concatenate(([False], nearest_wells == wi, [False]))
        idx = np.argwhere(np.diff(np.array(near_well, dtype=float)) == 1)
        idx2 = np.argwhere(np.diff(np.array(near_well, dtype=float)) == -1) - 1
        entry_idxs.append(idx.T[0])
        exit_idxs.append(idx2.T[0])
        entry_times.append(ts[idx.T[0]])
        exit_times.append(ts[idx2.T[0]])

    return entry_idxs, exit_idxs, entry_times, exit_times


def getSingleWellEntryAndExitTimes(xs, ys, ts, wellx, welly):
    """
    returns tuple of entry and exit times
    """
    # Note nan values are filled in. Cannot use nan as a valid way to
    # mask part of the values, just pass in the relevant portions
    xs = np.array(xs)
    ys = np.array(ys)
    ts = np.array(ts)
    nanmask = np.logical_or(np.isnan(xs), np.isnan(ys))
    notnanmask = np.logical_not(nanmask)
    xs[nanmask] = np.interp(ts[nanmask], ts[notnanmask], xs[notnanmask])
    ys[nanmask] = np.interp(ts[nanmask], ts[notnanmask], ys[notnanmask])
    dist_to_well = np.sqrt(np.power(wellx - np.array(xs), 2) +
                           np.power(welly - np.array(ys), 2))

    near_well = dist_to_well < RADIUS
    idx = np.argwhere(np.diff(np.array(near_well, dtype=float)) == 1)
    idx2 = np.argwhere(np.diff(np.array(near_well, dtype=float)) == -1)
    return ts[idx.T[0]], ts[idx2.T[0]]


# 2 3
# 0 1
def quadrantOfWell(well_idx):
    if well_idx > 24:
        res = 2
    else:
        res = 0

    if (well_idx - 1) % 8 >= 4:
        res += 1

    return res


def getListOfVisitedWells(nearestWells, countFirstVisitOnly):
    if countFirstVisitOnly:
        return list(set(nearestWells))
    else:
        return [k for k, g in groupby(nearestWells)]


if __name__ == "__main__":
    dataob = BTData()

    # ===================================
    # Filter to just relevant directories
    # ===================================
    filtered_data_dirs = []
    prevSessionDirs = []
    prevSession = None
    for session_idx, session_dir in enumerate(all_data_dirs):
        if session_dir == "behavior_notes" or "numpy_objs" in session_dir:
            continue

        if not os.path.isdir(os.path.join(data_dir, session_dir)):
            print("skipping this file ... dirs only")
            continue

        dir_split = session_dir.split('_')
        if dir_split[-1] == "Probe" or dir_split[-1] == "ITI":
            # will deal with this in another loop
            print("skipping, is probe or iti")
            continue

        date_str = dir_split[0][-8:]

        if RUN_JUST_SPECIFIED and date_str not in SPECIFIED_DAYS:
            continue

        if date_str in excluded_dates:
            print("skipping, excluded date")
            prevSession = session_dir
            continue

        filtered_data_dirs.append(session_dir)
        prevSessionDirs.append(prevSession)

    print("\n".join(filtered_data_dirs))

    for session_idx, session_dir in enumerate(filtered_data_dirs):

        # ======================================================================
        # ===================================
        # Create new session and import raw data
        # ===================================
        # ======================================================================
        session = BTSession()

        dir_split = session_dir.split('_')
        date_str = dir_split[0][-8:]
        time_str = dir_split[1]
        session_name_pfx = dir_split[0][0:-8]
        session.date_str = date_str
        session.name = session_dir
        session.time_str = time_str
        s = "{}_{}".format(date_str, time_str)
        print(s)
        session.date = datetime.strptime(s, "%Y%m%d_%H%M%S")
        print(session.date)

        session.prevSessionDir = prevSessionDirs[session_idx]

        # check for files that belong to this date
        session.bt_dir = session_dir
        gl = data_dir + session_name_pfx + date_str + "*"
        dir_list = glob.glob(gl)
        for d in dir_list:
            if d.split('_')[-1] == "ITI":
                session.iti_dir = d
                session.separate_iti_file = True
                session.recorded_iti = True
            elif d.split('_')[-1] == "Probe":
                session.probe_dir = d
                session.separate_probe_file = True

        if not session.separate_probe_file:
            session.recorded_iti = True
            session.probe_dir = os.path.join(data_dir, session_dir)
        if not session.separate_iti_file and session.recorded_iti:
            session.iti_dir = session_dir

        file_str = os.path.join(data_dir, session_dir, session_dir)
        all_lfp_data = []
        session.bt_lfp_fnames = []

        position_data = readRawPositionData(
            file_str + '.1.videoPositionTracking')
        if session.separate_probe_file:
            probe_file_str = os.path.join(
                session.probe_dir, os.path.basename(session.probe_dir))
            bt_time_clips = readClipData(file_str + '.1.clips')[0]
            probe_time_clips = readClipData(probe_file_str + '.1.clips')[0]
        else:
            time_clips = readClipData(file_str + '.1.clips')
            bt_time_clips = time_clips[0]
            probe_time_clips = time_clips[1]

        xs, ys, ts = processPosData(position_data)
        bt_start_idx = np.searchsorted(ts, bt_time_clips[0])
        bt_end_idx = np.searchsorted(ts, bt_time_clips[1])
        session.bt_pos_xs = xs[bt_start_idx:bt_end_idx]
        session.bt_pos_ys = ys[bt_start_idx:bt_end_idx]
        session.bt_pos_ts = ts[bt_start_idx:bt_end_idx]

        if session.separate_probe_file:
            position_data = readRawPositionData(
                probe_file_str + '.1.videoPositionTracking')
            xs, ys, ts = processPosData(position_data)

        probe_start_idx = np.searchsorted(ts, probe_time_clips[0])
        probe_end_idx = np.searchsorted(ts, probe_time_clips[1])
        session.probe_pos_xs = xs[probe_start_idx:probe_end_idx]
        session.probe_pos_ys = ys[probe_start_idx:probe_end_idx]
        session.probe_pos_ts = ts[probe_start_idx:probe_end_idx]

        # ===================================
        # Get flags and info from info file
        # ===================================
        info_file = os.path.join(behavior_notes_dir, date_str + ".txt")
        if not os.path.exists(info_file):
            # Switched numbering scheme once started doing multiple sessions a day
            seshs_on_this_day = sorted(
                list(filter(lambda seshdir: session.date_str + "_" in seshdir, filtered_data_dirs)))
            num_on_this_day = len(seshs_on_this_day)
            for i in range(num_on_this_day):
                if seshs_on_this_day[i] == session_dir:
                    sesh_idx_within_day = i
            info_file = os.path.join(behavior_notes_dir, date_str + "_" +
                                     str(sesh_idx_within_day+1) + ".txt")

        if "".join(os.path.basename(info_file).split(".")[0:-1]) in excluded_sessions:
            print(session_dir, " excluded session, skipping")
            continue

        prevsession_dir = prevSessionDirs[session_idx]
        prevdir_split = prevsession_dir.split('_')
        prevdate_str = prevdir_split[0][-8:]
        prevSessionInfoFile = os.path.join(behavior_notes_dir, prevdate_str + ".txt")
        if not os.path.exists(prevSessionInfoFile):
            # Switched numbering scheme once started doing multiple sessions a day
            seshs_on_this_day = sorted(
                list(filter(lambda seshdir: session.date_str + "_" in seshdir, filtered_data_dirs)))
            num_on_this_day = len(seshs_on_this_day)
            for i in range(num_on_this_day):
                if seshs_on_this_day[i] == prevsession_dir:
                    sesh_idx_within_day = i
            prevSessionInfoFile = os.path.join(behavior_notes_dir, prevdate_str + "_" +
                                               str(sesh_idx_within_day+1) + ".txt")

        try:
            with open(info_file, 'r') as f:
                lines = f.readlines()
                for line in lines:
                    lineparts = line.split(":")
                    if len(lineparts) != 2:
                        session.notes.append(line)
                        continue

                    field_name = lineparts[0]
                    field_val = lineparts[1]

                    if field_name.lower() == "home":
                        session.home_well = int(field_val)
                    elif field_name.lower() == "aways":
                        session.away_wells = [int(w)
                                              for w in field_val.strip().split(' ')]
                        # print(line)
                        # print(field_name, field_val)
                        # print(session.away_wells)
                    elif field_name.lower() == "condition":
                        type_in = field_val
                        if 'Ripple' in type_in or 'Interruption' in type_in:
                            session.isRippleInterruption = True
                        elif 'None' in type_in:
                            session.isNoInterruption = True
                        elif 'Delayed' in type_in:
                            session.isDelayedInterruption = True
                        else:
                            print("Couldn't recognize Condition {} in file {}".format(
                                type_in, info_file))
                    elif field_name.lower() == "thresh":
                        if "Low" in field_val:
                            session.ripple_detection_threshold = 2.5
                        elif "High" in field_val:
                            session.ripple_detection_threshold = 4
                        else:
                            session.ripple_detection_threshold = float(
                                field_val)
                    elif field_name.lower() == "last away":
                        session.last_away_well = float(field_val)
                        # print(field_val)
                    elif field_name.lower() == "last well":
                        ended_on = field_val
                        if 'H' in field_val:
                            session.ended_on_home = True
                        elif 'A' in field_val:
                            session.ended_on_home = False
                        else:
                            print("Couldn't recognize last well {} in file {}".format(
                                field_val, info_file))
                    elif field_name.lower() == "iti stim on":
                        if 'Y' in field_val:
                            session.ITI_stim_on = True
                        elif 'N' in field_val:
                            session.ITI_stim_on = False
                        else:
                            print("Couldn't recognize ITI Stim condition {} in file {}".format(
                                field_val, info_file))
                    elif field_name.lower() == "probe stim on":
                        if 'Y' in field_val:
                            session.probe_stim_on = True
                        elif 'N' in field_val:
                            session.probe_stim_on = False
                        else:
                            print("Couldn't recognize Probe Stim condition {} in file {}".format(
                                field_val, info_file))
                    else:
                        session.notes.append(line)

        except FileNotFoundError as err:
            print(err)
            print("Couldn't read from info file " + info_file)
            # cbool = input("Would you like to skip this session (Y/N)?")
            # if cbool.lower() == "y":
            # continue
            continue

            print("Getting some info by hand")
            session.home_well = 0
            while session.home_well < 1 or session.home_well > 48:
                # session.home_well = int(input("Home well:"))
                session.home_well = 10

            type_in = 'X'
            while not (type_in in ['R', 'N', 'D']):
                # type_in = input(
                # "Type of trial ([R]ipple interruption/[N]o stim/[D]elayed stim):").upper()
                type_in = 'R'

            if type_in == 'R':
                session.isRippleInterruption = True
            elif type_in == 'N':
                session.isNoInterruption = True
            elif type_in == 'D':
                session.isDelayedInterruption = True

        except Exception as err:
            print(info_file)
            raise err

        try:
            with open(prevSessionInfoFile, 'r') as f:
                session.prevSessionInfoParsed = True
                lines = f.readlines()
                for line in lines:
                    lineparts = line.split(":")
                    if len(lineparts) != 2:
                        continue

                    field_name = lineparts[0]
                    field_val = lineparts[1]

                    if field_name.lower() == "home":
                        session.prevSessionHome = int(field_val)
                    elif field_name.lower() == "aways":
                        session.prevSessionAways = [int(w)
                                                    for w in field_val.strip().split(' ')]
                    elif field_name.lower() == "condition":
                        type_in = field_val
                        if 'Ripple' in type_in or 'Interruption' in type_in:
                            session.prevSessionIsRippleInterruption = True
                        elif 'None' in type_in:
                            session.prevSessionIsNoInterruption = True
                        elif 'Delayed' in type_in:
                            session.prevSessionIsDelayedInterruption = True
                        else:
                            print("Couldn't recognize Condition {} in file {}".format(
                                type_in, prevSessionInfoFile))
                    elif field_name.lower() == "thresh":
                        if "Low" in field_val:
                            session.prevSession_ripple_detection_threshold = 2.5
                        elif "High" in field_val:
                            session.prevSession_ripple_detection_threshold = 4
                        else:
                            session.prevSession_ripple_detection_threshold = float(
                                field_val)
                    elif field_name.lower() == "last away":
                        session.prevSession_last_away_well = float(field_val)
                        # print(field_val)
                    elif field_name.lower() == "last well":
                        ended_on = field_val
                        if 'H' in field_val:
                            session.prevSession_ended_on_home = True
                        elif 'A' in field_val:
                            session.prevSession_ended_on_home = False
                        else:
                            print("Couldn't recognize last well {} in file {}".format(
                                field_val, prevSessionInfoFile))
                    elif field_name.lower() == "iti stim on":
                        if 'Y' in field_val:
                            session.prevSession_ITI_stim_on = True
                        elif 'N' in field_val:
                            session.prevSession_ITI_stim_on = False
                        else:
                            print("Couldn't recognize ITI Stim condition {} in file {}".format(
                                field_val, prevSessionInfoFile))
                    elif field_name.lower() == "probe stim on":
                        if 'Y' in field_val:
                            session.prevSession_probe_stim_on = True
                        elif 'N' in field_val:
                            session.prevSession_probe_stim_on = False
                        else:
                            print("Couldn't recognize Probe Stim condition {} in file {}".format(
                                field_val, prevSessionInfoFile))
                    else:
                        pass

        except FileNotFoundError as err:
            session.prevSessionInfoParsed = False
            print("Couldn't read from prev session info file " + prevSessionInfoFile)

        if session.home_well == 0:
            print("Home well not listed in notes file, skipping")
            continue

        well_coords_file_name = file_str + '.1.wellLocations.csv'
        session.well_coords_map = readWellCoordsFile(well_coords_file_name)
        session.home_x, session.home_y = get_well_coordinates(
            session.home_well, session.well_coords_map)

        # for i in range(len(session.ripple_detection_tetrodes)):
        #     spkdir = file_str + ".spikes"
        #     if not os.path.exists(spkdir):
        #         print(spkdir, "doesn't exists, gonna try and extract the spikes")
        #         syscmd = "/home/wcroughan/SpikeGadgets/Trodes_1_8_1/exportspikes -rec " + file_str + ".rec"
        #         print(syscmd)
        #         os.system(syscmd)

        for i in range(len(session.ripple_detection_tetrodes)):
            lfpdir = file_str + ".LFP"
            if not os.path.exists(lfpdir):
                print(lfpdir, "doesn't exists, gonna try and extract the LFP")
                # syscmd = "/home/wcroughan/SpikeGadgets/Trodes_1_8_1/exportLFP -rec " + file_str + ".rec"
                syscmd = "/home/wcroughan/Software/Trodes21/exportLFP -rec " + file_str + ".rec"
                print(syscmd)
                os.system(syscmd)
            session.bt_lfp_fnames.append(os.path.join(file_str + ".LFP", session_dir +
                                                      ".LFP_nt" + str(session.ripple_detection_tetrodes[i]) + "ch1.dat"))
            all_lfp_data.append(MountainViewIO.loadLFP(data_file=session.bt_lfp_fnames[-1]))

        # ======================================================================
        # ===================================
        # Analyze data
        # ===================================
        # ======================================================================

        # ===================================
        # LFP
        # ===================================
        lfp_data = all_lfp_data[0][1]['voltage']
        lfp_timestamps = all_lfp_data[0][0]['time']

        lfp_deflections = signal.find_peaks(-lfp_data, height=DEFLECTION_THRESHOLD_HI,
                                            distance=MIN_ARTIFACT_DISTANCE)
        interruption_idxs = lfp_deflections[0]
        session.interruption_timestamps = lfp_timestamps[interruption_idxs]

        lfp_deflections = signal.find_peaks(np.abs(
            np.diff(lfp_data, prepend=lfp_data[0])), height=DEFLECTION_THRESHOLD_LO, distance=MIN_ARTIFACT_DISTANCE)
        lfp_artifact_idxs = lfp_deflections[0]
        session.artifact_timestamps = lfp_timestamps[lfp_artifact_idxs]

        # ripple_power = get_ripple_power(lfp_data, omit_artifacts=True,
        #                                 causal_smoothing=False, lfp_deflections=lfp_artifact_idxs)

        # ripple_power = ripple_power[0]
        # # ripple_power /= np.nanmax(ripple_power)
        # # ripple_power *= np.nanmax(lfp_data)

        # lfp_diff = np.diff(lfp_data, prepend=lfp_data[0])

        # plt.clf()
        # plt.plot(lfp_timestamps, lfp_data)
        # # # # plt.plot(lfp_timestamps, np.abs(lfp_diff))
        # # # plt.plot(lfp_timestamps, ripple_power)
        # plt.scatter(lfp_timestamps[lfp_artifact_idxs],
        #             # #             # np.abs(lfp_diff[lfp_artifact_idxs]), c=[[1, 0, 0, 1]], zorder=30)
        #             lfp_data[lfp_artifact_idxs], c=[[1, 0, 0, 1]], zorder=30)

        # if session.isDelayedInterruption:
        #     type_txt = 'Delayed'
        # elif session.isNoInterruption:
        #     type_txt = 'None'
        # elif session.isRippleInterruption:
        #     type_txt = 'Ripple'
        # else:
        #     type_txt = 'unknown'
        #     print("unknown session type")
        # plt.text(1, 1, type_txt, horizontalalignment='right',
        #          verticalalignment='top', transform=plt.gca().transAxes)
        # plt.show()

        # ARP_SZ = int(0.3 * float(LFP_SAMPLING_RATE))
        # aligned_rip_power = np.empty((len(interruption_idxs), ARP_SZ))
        # for ai, a in enumerate(interruption_idxs):
        #     aligned_rip_power[ai, :] = ripple_power[a - ARP_SZ:a]

        # avg_arp = np.nanmean(aligned_rip_power, axis=0)

        # xvals = np.linspace(-300, 0, ARP_SZ)
        # # plt.clf()
        # # plt.plot(xvals, avg_arp)
        # # plt.text(1, 1, type_txt, horizontalalignment='right',
        # #          verticalalignment='top', transform=plt.gca().transAxes)
        # # plt.text(1, 0.9, str(len(all_lfp_data)), horizontalalignment='right',
        # #          verticalalignment='top', transform=plt.gca().transAxes)
        # # plt.show()

        # continue

        # ===================================
        # which away wells were visited?
        # ===================================
        session.num_away_found = next((i for i in range(
            len(session.away_wells)) if session.away_wells[i] == session.last_away_well), -1) + 1
        session.visited_away_wells = session.away_wells[0:session.num_away_found]
        # print(session.last_away_well)
        session.num_home_found = session.num_away_found
        if session.ended_on_home:
            session.num_home_found += 1

        # ===================================
        # Well visit times
        # ===================================
        rewardClipsFile = file_str + '.1.rewardClips'
        if not os.path.exists(rewardClipsFile):
            print("Well find times not marked for session {}".format(session.name))
        else:
            well_visit_times = readClipData(rewardClipsFile)
            assert session.num_away_found + \
                session.num_home_found == np.shape(well_visit_times)[0]
            session.home_well_find_times = well_visit_times[::2, 0]
            session.home_well_leave_times = well_visit_times[::2, 1]
            session.away_well_find_times = well_visit_times[1::2, 0]
            session.away_well_leave_times = well_visit_times[1::2, 1]

            session.home_well_find_pos_idxs = np.searchsorted(
                session.bt_pos_ts, session.home_well_find_times)
            session.home_well_leave_pos_idxs = np.searchsorted(
                session.bt_pos_ts, session.home_well_leave_times)
            session.away_well_find_pos_idxs = np.searchsorted(
                session.bt_pos_ts, session.away_well_find_times)
            session.away_well_leave_pos_idxs = np.searchsorted(
                session.bt_pos_ts, session.away_well_leave_times)

            if len(session.home_well_leave_times) == len(session.away_well_find_times):
                session.away_well_latencies = np.array(session.away_well_find_times) - \
                    np.array(session.home_well_leave_times)
                session.home_well_latencies = np.array(session.home_well_find_times) - \
                    np.append([session.bt_pos_ts[0]],
                              session.away_well_leave_times[0:-1])
            else:
                session.away_well_latencies = np.array(session.away_well_find_times) - \
                    np.array(session.home_well_leave_times[0:-1])
                session.home_well_latencies = np.array(session.home_well_find_times) - \
                    np.append([session.bt_pos_ts[0]],
                              session.away_well_leave_times)

        # ===================================
        # separating movement time from still time
        # ===================================
        bt_vel = np.sqrt(np.power(np.diff(session.bt_pos_xs), 2) +
                         np.power(np.diff(session.bt_pos_ys), 2))
        session.bt_vel_cm_s = np.divide(bt_vel, np.diff(session.bt_pos_ts) /
                                        TRODES_SAMPLING_RATE) / PIXELS_PER_CM
        bt_is_mv = session.bt_vel_cm_s > VEL_THRESH
        bt_is_mv = np.append(bt_is_mv, np.array(bt_is_mv[-1]))
        session.bt_is_mv = bt_is_mv
        session.bt_mv_xs = np.array(session.bt_pos_xs)
        session.bt_mv_xs[np.logical_not(bt_is_mv)] = np.nan
        session.bt_still_xs = np.array(session.bt_pos_xs)
        session.bt_still_xs[bt_is_mv] = np.nan
        session.bt_mv_ys = np.array(session.bt_pos_ys)
        session.bt_mv_ys[np.logical_not(bt_is_mv)] = np.nan
        session.bt_still_ys = np.array(session.bt_pos_ys)
        session.bt_still_ys[bt_is_mv] = np.nan

        probe_vel = np.sqrt(np.power(np.diff(session.probe_pos_xs), 2) +
                            np.power(np.diff(session.probe_pos_ys), 2))
        session.probe_vel_cm_s = np.divide(probe_vel, np.diff(session.probe_pos_ts) /
                                           TRODES_SAMPLING_RATE) / PIXELS_PER_CM
        probe_is_mv = session.probe_vel_cm_s > VEL_THRESH
        probe_is_mv = np.append(probe_is_mv, np.array(probe_is_mv[-1]))
        session.probe_is_mv = probe_is_mv
        session.probe_mv_xs = np.array(session.probe_pos_xs)
        session.probe_mv_xs[np.logical_not(probe_is_mv)] = np.nan
        session.probe_still_xs = np.array(session.probe_pos_xs)
        session.probe_still_xs[probe_is_mv] = np.nan
        session.probe_mv_ys = np.array(session.probe_pos_ys)
        session.probe_mv_ys[np.logical_not(probe_is_mv)] = np.nan
        session.probe_still_ys = np.array(session.probe_pos_ys)
        session.probe_still_ys[probe_is_mv] = np.nan

        # ===================================
        # Perseveration measures
        # ===================================
        session.ctrl_home_well = 49 - session.home_well
        session.ctrl_home_x, session.ctrl_home_y = get_well_coordinates(
            session.ctrl_home_well, session.well_coords_map)

        # ===================================
        # Well and quadrant entry and exit times
        # ===================================
        session.bt_nearest_wells = getNearestWell(
            session.bt_pos_xs, session.bt_pos_ys, session.well_coords_map)

        session.bt_quadrants = np.array(
            [quadrantOfWell(wi) for wi in session.bt_nearest_wells])
        session.home_quadrant = quadrantOfWell(session.home_well)

        session.bt_well_entry_idxs, session.bt_well_exit_idxs, \
            session.bt_well_entry_times, session.bt_well_exit_times = \
            getWellEntryAndExitTimes(
                session.bt_nearest_wells, session.bt_pos_ts)

        # ninc stands for neighbors included
        session.bt_well_entry_idxs_ninc, session.bt_well_exit_idxs_ninc, \
            session.bt_well_entry_times_ninc, session.bt_well_exit_times_ninc = \
            getWellEntryAndExitTimes(
                session.bt_nearest_wells, session.bt_pos_ts, include_neighbors=True)

        session.bt_quadrant_entry_idxs, session.bt_quadrant_exit_idxs, \
            session.bt_quadrant_entry_times, session.bt_quadrant_exit_times = \
            getWellEntryAndExitTimes(
                session.bt_quadrants, session.bt_pos_ts, well_idxs=[0, 1, 2, 3])

        for i in range(len(all_well_names)):
            # print("well {} had {} entries, {} exits".format(
            #     all_well_names[i], len(session.bt_well_entry_idxs[i]), len(session.bt_well_exit_idxs[i])))
            assert len(session.bt_well_entry_times[i]) == len(
                session.bt_well_exit_times[i])

        session.home_well_idx_in_allwells = np.argmax(
            all_well_names == session.home_well)
        session.ctrl_home_well_idx_in_allwells = np.argmax(
            all_well_names == session.ctrl_home_well)

        session.bt_home_well_entry_times = session.bt_well_entry_times[
            session.home_well_idx_in_allwells]
        session.bt_home_well_exit_times = session.bt_well_exit_times[
            session.home_well_idx_in_allwells]

        session.bt_ctrl_home_well_entry_times = session.bt_well_entry_times[
            session.ctrl_home_well_idx_in_allwells]
        session.bt_ctrl_home_well_exit_times = session.bt_well_exit_times[
            session.ctrl_home_well_idx_in_allwells]

        # same for during probe
        session.probe_nearest_wells = getNearestWell(
            session.probe_pos_xs, session.probe_pos_ys, session.well_coords_map)

        session.probe_well_entry_idxs, session.probe_well_exit_idxs, \
            session.probe_well_entry_times, session.probe_well_exit_times = getWellEntryAndExitTimes(
                session.probe_nearest_wells, session.probe_pos_ts)

        session.probe_well_entry_idxs_ninc, session.probe_well_exit_idxs_ninc, \
            session.probe_well_entry_times_ninc, session.probe_well_exit_times_ninc = getWellEntryAndExitTimes(
                session.probe_nearest_wells, session.probe_pos_ts, include_neighbors=True)

        session.probe_quadrants = np.array(
            [quadrantOfWell(wi) for wi in session.probe_nearest_wells])

        session.probe_quadrant_entry_idxs, session.probe_quadrant_exit_idxs, \
            session.probe_quadrant_entry_times, session.probe_quadrant_exit_times = getWellEntryAndExitTimes(
                session.probe_quadrants, session.probe_pos_ts, well_idxs=[0, 1, 2, 3])

        for i in range(len(all_well_names)):
            # print(i, len(session.probe_well_entry_times[i]), len(session.probe_well_exit_times[i]))
            assert len(session.probe_well_entry_times[i]) == len(
                session.probe_well_exit_times[i])

        session.probe_home_well_entry_times = session.probe_well_entry_times[
            session.home_well_idx_in_allwells]
        session.probe_home_well_exit_times = session.probe_well_exit_times[
            session.home_well_idx_in_allwells]

        session.probe_ctrl_home_well_entry_times = session.probe_well_entry_times[
            session.ctrl_home_well_idx_in_allwells]
        session.probe_ctrl_home_well_exit_times = session.probe_well_exit_times[
            session.ctrl_home_well_idx_in_allwells]

        # ===================================
        # Sniff times marked by hand from USB camera (Not available for Martin)
        # ===================================

        sniffTimesFile = file_str + '.rgs'
        if not os.path.exists(sniffTimesFile):
            print("Please save your sniff regions file to {}".format(sniffTimesFile))
        else:
            streader = csv.reader(sniffTimesFile)
            sniffData = list(streader)

            session.well_sniff_times_entry = [[] for _ in all_well_names]

            session.sniff_pre_trial_light_off = sniffData[0][0]
            session.sniff_trial_start = sniffData[0][1]
            session.sniff_trial_stop = sniffData[0][2]
            session.sniff_probe_start = sniffData[1][0]
            session.sniff_probe_stop = sniffData[1][1]
            session.sniff_post_probe_light_on = sniffData[1][2]

            for i in sniffData[2:]:
                session.well_sniff_times_entry[well_name_to_idx[int(i[2])]].append(int(i[0]))
                session.well_sniff_times_exit[well_name_to_idx[int(i[2])]].append(int(i[1]))

        # ===================================
        # Ballisticity of movements
        # ===================================

        furthest_interval = max(BALL_TIME_INTERVALS)
        assert np.all(np.diff(np.array(BALL_TIME_INTERVALS)) > 0)
        assert BALL_TIME_INTERVALS[0] > 0

        # idx is (time, interval len, dimension)
        d1 = len(session.bt_pos_ts) - furthest_interval
        delta = np.empty((d1, furthest_interval, 2))
        delta[:] = np.nan
        dx = np.diff(session.bt_pos_xs)
        dy = np.diff(session.bt_pos_ys)
        delta[:, 0, 0] = dx[0:d1]
        delta[:, 0, 1] = dy[0:d1]

        for i in range(1, furthest_interval):
            delta[:, i, 0] = delta[:, i-1, 0] + dx[i:i+d1]
            delta[:, i, 1] = delta[:, i-1, 1] + dy[i:i+d1]

        displacement = np.sqrt(np.sum(np.square(delta), axis=2))
        last_displacement = displacement[:, -1]
        session.bt_ball_displacement = last_displacement

        x = np.log(np.tile(np.arange(furthest_interval) + 1, (d1, 1)))
        y = np.log(displacement)
        assert np.all(np.logical_or(
            np.logical_not(np.isnan(y)), displacement == 0))
        y[y == -np.inf] = np.nan
        np.nan_to_num(y, copy=False, nan=np.nanmin(y))

        x = x - np.tile(np.nanmean(x, axis=1), (furthest_interval, 1)).T
        y = y - np.tile(np.nanmean(y, axis=1), (furthest_interval, 1)).T
        def m(arg): return np.mean(arg, axis=1)
        # beta = ((m(y * x) - m(x) * m(y))/m(x*x) - m(x)**2)
        beta = m(y*x)/m(np.power(x, 2))
        session.bt_ballisticity = beta
        assert np.sum(np.isnan(session.bt_ballisticity)) == 0

        # idx is (time, interval len, dimension)
        d1 = len(session.probe_pos_ts) - furthest_interval
        delta = np.empty((d1, furthest_interval, 2))
        delta[:] = np.nan
        dx = np.diff(session.probe_pos_xs)
        dy = np.diff(session.probe_pos_ys)
        delta[:, 0, 0] = dx[0:d1]
        delta[:, 0, 1] = dy[0:d1]

        for i in range(1, furthest_interval):
            delta[:, i, 0] = delta[:, i-1, 0] + dx[i:i+d1]
            delta[:, i, 1] = delta[:, i-1, 1] + dy[i:i+d1]

        displacement = np.sqrt(np.sum(np.square(delta), axis=2))
        last_displacement = displacement[:, -1]
        session.probe_ball_displacement = last_displacement

        x = np.log(np.tile(np.arange(furthest_interval) + 1, (d1, 1)))
        y = np.log(displacement)
        assert np.all(np.logical_or(
            np.logical_not(np.isnan(y)), displacement == 0))
        y[y == -np.inf] = np.nan
        np.nan_to_num(y, copy=False, nan=np.nanmin(y))

        x = x - np.tile(np.nanmean(x, axis=1), (furthest_interval, 1)).T
        y = y - np.tile(np.nanmean(y, axis=1), (furthest_interval, 1)).T
        # beta = ((m(y * x) - m(x) * m(y))/m(x*x) - m(x)**2)
        beta = m(y*x)/m(np.power(x, 2))
        session.probe_ballisticity = beta
        assert np.sum(np.isnan(session.probe_ballisticity)) == 0

        # ===================================
        # Knot-path-curvature as in https://journals.plos.org/ploscompbiol/article?id=10.1371/journal.pcbi.1000638
        # ===================================

        dx = np.diff(session.bt_pos_xs)
        dy = np.diff(session.bt_pos_ys)

        if SHOW_CURVATURE_VIDEO:
            cmap = plt.cm.get_cmap('coolwarm')
            fig = plt.figure()
            plt.ion()

        session.bt_curvature = np.empty((dx.size+1))
        session.bt_curvature_i1 = np.empty((dx.size+1))
        session.bt_curvature_i2 = np.empty((dx.size+1))
        session.bt_curvature_dxf = np.empty((dx.size+1))
        session.bt_curvature_dyf = np.empty((dx.size+1))
        session.bt_curvature_dxb = np.empty((dx.size+1))
        session.bt_curvature_dyb = np.empty((dx.size+1))
        for pi in range(dx.size+1):
            x0 = session.bt_pos_xs[pi]
            y0 = session.bt_pos_ys[pi]
            ii = pi
            dxf = 0.0
            dyf = 0.0
            while ii < dx.size:
                dxf += dx[ii]
                dyf += dy[ii]
                magf = dxf * dxf + dyf * dyf
                if magf >= KNOT_H_POS * KNOT_H_POS:
                    break
                ii += 1
            if ii == dx.size:
                session.bt_curvature[pi] = np.nan
                session.bt_curvature_i1[pi] = np.nan
                session.bt_curvature_i2[pi] = np.nan
                session.bt_curvature_dxf[pi] = np.nan
                session.bt_curvature_dyf[pi] = np.nan
                session.bt_curvature_dxb[pi] = np.nan
                session.bt_curvature_dyb[pi] = np.nan
                continue
            i2 = ii

            ii = pi - 1
            dxb = 0.0
            dyb = 0.0
            while ii >= 0:
                dxb += dx[ii]
                dyb += dy[ii]
                magb = dxb * dxb + dyb * dyb
                if magb >= KNOT_H_POS * KNOT_H_POS:
                    break
                ii -= 1
            if ii == -1:
                session.bt_curvature[pi] = np.nan
                session.bt_curvature_i1[pi] = np.nan
                session.bt_curvature_i2[pi] = np.nan
                session.bt_curvature_dxf[pi] = np.nan
                session.bt_curvature_dyf[pi] = np.nan
                session.bt_curvature_dxb[pi] = np.nan
                session.bt_curvature_dyb[pi] = np.nan
                continue
            i1 = ii

            uxf = dxf / np.sqrt(magf)
            uyf = dyf / np.sqrt(magf)
            uxb = dxb / np.sqrt(magb)
            uyb = dyb / np.sqrt(magb)
            dotprod = uxf * uxb + uyf * uyb
            session.bt_curvature[pi] = np.arccos(dotprod)

            session.bt_curvature_i1[pi] = i1
            session.bt_curvature_i2[pi] = i2
            session.bt_curvature_dxf[pi] = dxf
            session.bt_curvature_dyf[pi] = dyf
            session.bt_curvature_dxb[pi] = dxb
            session.bt_curvature_dyb[pi] = dyb

            if SHOW_CURVATURE_VIDEO:
                plt.clf()
                plt.xlim(0, 1200)
                plt.ylim(0, 1000)
                plt.plot(session.bt_pos_xs[i1:i2], session.bt_pos_ys[i1:i2])
                c = np.array(
                    cmap(session.bt_curvature[pi] / 3.15)).reshape(1, -1)
                plt.scatter(session.bt_pos_xs[pi], session.bt_pos_ys[pi], c=c)
                plt.show()
                plt.pause(0.01)

        dx = np.diff(session.probe_pos_xs)
        dy = np.diff(session.probe_pos_ys)

        session.probe_curvature = np.empty((dx.size+1))
        session.probe_curvature_i1 = np.empty((dx.size+1))
        session.probe_curvature_i2 = np.empty((dx.size+1))
        session.probe_curvature_dxf = np.empty((dx.size+1))
        session.probe_curvature_dyf = np.empty((dx.size+1))
        session.probe_curvature_dxb = np.empty((dx.size+1))
        session.probe_curvature_dyb = np.empty((dx.size+1))
        for pi in range(dx.size+1):
            x0 = session.probe_pos_xs[pi]
            y0 = session.probe_pos_ys[pi]
            ii = pi
            dxf = 0.0
            dyf = 0.0
            while ii < dx.size:
                dxf += dx[ii]
                dyf += dy[ii]
                magf = np.sqrt(dxf * dxf + dyf * dyf)
                if magf >= KNOT_H_POS:
                    break
                ii += 1
            if ii == dx.size:
                session.probe_curvature[pi] = np.nan
                session.probe_curvature_i1[pi] = np.nan
                session.probe_curvature_i2[pi] = np.nan
                session.probe_curvature_dxf[pi] = np.nan
                session.probe_curvature_dyf[pi] = np.nan
                session.probe_curvature_dxb[pi] = np.nan
                session.probe_curvature_dyb[pi] = np.nan
                continue
            i2 = ii

            ii = pi - 1
            dxb = 0.0
            dyb = 0.0
            while ii >= 0:
                dxb += dx[ii]
                dyb += dy[ii]
                magb = np.sqrt(dxb * dxb + dyb * dyb)
                if magb >= KNOT_H_POS:
                    break
                ii -= 1
            if ii == -1:
                session.probe_curvature[pi] = np.nan
                session.probe_curvature_i1[pi] = np.nan
                session.probe_curvature_i2[pi] = np.nan
                session.probe_curvature_dxf[pi] = np.nan
                session.probe_curvature_dyf[pi] = np.nan
                session.probe_curvature_dxb[pi] = np.nan
                session.probe_curvature_dyb[pi] = np.nan
                continue
            i1 = ii

            uxf = dxf / magf
            uyf = dyf / magf
            uxb = dxb / magb
            uyb = dyb / magb
            dotprod = uxf * uxb + uyf * uyb
            session.probe_curvature[pi] = np.arccos(dotprod)

            session.probe_curvature_i1[pi] = i1
            session.probe_curvature_i2[pi] = i2
            session.probe_curvature_dxf[pi] = dxf
            session.probe_curvature_dyf[pi] = dyf
            session.probe_curvature_dxb[pi] = dxb
            session.probe_curvature_dyb[pi] = dyb

        session.bt_well_curvatures = []
        session.bt_well_avg_curvature_over_time = []
        session.bt_well_avg_curvature_over_visits = []
        for i, wi in enumerate(all_well_names):
            session.bt_well_curvatures.append([])
            for ei, (weni, wexi) in enumerate(zip(session.bt_well_entry_idxs[i], session.bt_well_exit_idxs[i])):
                if wexi > session.bt_curvature.size:
                    continue
                session.bt_well_curvatures[i].append(
                    session.bt_curvature[weni:wexi])

            session.bt_well_avg_curvature_over_time.append(
                np.mean(np.concatenate(session.bt_well_curvatures[i])))
            session.bt_well_avg_curvature_over_visits.append(
                np.mean([np.mean(x) for x in session.bt_well_curvatures[i]]))

        session.probe_well_curvatures = []
        session.probe_well_avg_curvature_over_time = []
        session.probe_well_avg_curvature_over_visits = []
        session.probe_well_curvatures_1min = []
        session.probe_well_avg_curvature_over_time_1min = []
        session.probe_well_avg_curvature_over_visits_1min = []
        session.probe_well_curvatures_30sec = []
        session.probe_well_avg_curvature_over_time_30sec = []
        session.probe_well_avg_curvature_over_visits_30sec = []
        for i, wi in enumerate(all_well_names):
            session.probe_well_curvatures.append([])
            session.probe_well_curvatures_1min.append([])
            session.probe_well_curvatures_30sec.append([])
            for ei, (weni, wexi) in enumerate(zip(session.probe_well_entry_idxs[i], session.probe_well_exit_idxs[i])):
                if wexi > session.probe_curvature.size:
                    continue
                session.probe_well_curvatures[i].append(
                    session.probe_curvature[weni:wexi])
                if session.probe_pos_ts[weni] <= session.probe_pos_ts[0] + 60*TRODES_SAMPLING_RATE:
                    session.probe_well_curvatures_1min[i].append(
                        session.probe_curvature[weni:wexi])
                if session.probe_pos_ts[weni] <= session.probe_pos_ts[0] + 30*TRODES_SAMPLING_RATE:
                    session.probe_well_curvatures_30sec[i].append(
                        session.probe_curvature[weni:wexi])

            if len(session.probe_well_curvatures[i]) > 0:
                session.probe_well_avg_curvature_over_time.append(
                    np.mean(np.concatenate(session.probe_well_curvatures[i])))
                session.probe_well_avg_curvature_over_visits.append(
                    np.mean([np.mean(x) for x in session.probe_well_curvatures[i]]))
            else:
                session.probe_well_avg_curvature_over_time.append(np.nan)
                session.probe_well_avg_curvature_over_visits.append(np.nan)

            if len(session.probe_well_curvatures_1min[i]) > 0:
                session.probe_well_avg_curvature_over_time_1min.append(
                    np.mean(np.concatenate(session.probe_well_curvatures_1min[i])))
                session.probe_well_avg_curvature_over_visits_1min.append(
                    np.mean([np.mean(x) for x in session.probe_well_curvatures_1min[i]]))
            else:
                session.probe_well_avg_curvature_over_time_1min.append(np.nan)
                session.probe_well_avg_curvature_over_visits_1min.append(
                    np.nan)

            if len(session.probe_well_curvatures_30sec[i]) > 0:
                session.probe_well_avg_curvature_over_time_30sec.append(
                    np.mean(np.concatenate(session.probe_well_curvatures_30sec[i])))
                session.probe_well_avg_curvature_over_visits_30sec.append(
                    np.mean([np.mean(x) for x in session.probe_well_curvatures_30sec[i]]))
            else:
                session.probe_well_avg_curvature_over_time_30sec.append(np.nan)
                session.probe_well_avg_curvature_over_visits_30sec.append(
                    np.nan)

        # ===================================
        # Latency to well in probe
        # ===================================

        session.probe_latency_to_well = []
        for i, wi in enumerate(all_well_names):
            if len(session.probe_well_entry_times[i]) == 0:
                session.probe_latency_to_well.append(np.nan)
            else:
                session.probe_latency_to_well.append(
                    session.probe_well_entry_times[0])

        # ===================================
        # exploration bouts
        # ===================================

        POS_FRAME_RATE = stats.mode(
            np.diff(session.bt_pos_ts))[0] / float(TRODES_SAMPLING_RATE)
        BOUT_VEL_SM_SIGMA = BOUT_VEL_SM_SIGMA_SECS / POS_FRAME_RATE
        MIN_PAUSE_TIME_BETWEEN_BOUTS_SECS = 1.0
        MIN_PAUSE_TIME_FRAMES = int(
            MIN_PAUSE_TIME_BETWEEN_BOUTS_SECS / POS_FRAME_RATE)
        MIN_EXPLORE_TIME_FRAMES = int(MIN_EXPLORE_TIME_SECS / POS_FRAME_RATE)

        bt_sm_vel = scipy.ndimage.gaussian_filter1d(
            session.bt_vel_cm_s, BOUT_VEL_SM_SIGMA)
        session.bt_sm_vel = bt_sm_vel

        bt_is_explore_local = bt_sm_vel > PAUSE_MAX_SPEED_CM_S
        dil_filt = np.ones((MIN_PAUSE_TIME_FRAMES), dtype=int)
        in_pause_bout = np.logical_not(signal.convolve(
            bt_is_explore_local.astype(int), dil_filt, mode='same').astype(bool))
        # now just undo dilation to get flags
        session.bt_is_in_pause = signal.convolve(
            in_pause_bout.astype(int), dil_filt, mode='same').astype(bool)
        session.bt_is_in_explore = np.logical_not(session.bt_is_in_pause)

        # explicitly adjust flags at reward consumption times
        for wft, wlt in zip(session.home_well_find_times, session.home_well_leave_times):
            pidx1 = np.searchsorted(session.bt_pos_ts[0:-1], wft)
            pidx2 = np.searchsorted(session.bt_pos_ts[0:-1], wlt)
            session.bt_is_in_pause[pidx1:pidx2] = True
            session.bt_is_in_explore[pidx1:pidx2] = False

        for wft, wlt in zip(session.away_well_find_times, session.away_well_leave_times):
            pidx1 = np.searchsorted(session.bt_pos_ts[0:-1], wft)
            pidx2 = np.searchsorted(session.bt_pos_ts[0:-1], wlt)
            session.bt_is_in_pause[pidx1:pidx2] = True
            session.bt_is_in_explore[pidx1:pidx2] = False

        assert np.sum(np.isnan(session.bt_is_in_pause)) == 0
        assert np.sum(np.isnan(session.bt_is_in_explore)) == 0
        assert np.all(np.logical_or(
            session.bt_is_in_pause, session.bt_is_in_explore))
        assert not np.any(np.logical_and(
            session.bt_is_in_pause, session.bt_is_in_explore))

        start_explores = np.where(
            np.diff(session.bt_is_in_explore.astype(int)) == 1)[0] + 1
        if session.bt_is_in_explore[0]:
            start_explores = np.insert(start_explores, 0, 0)

        stop_explores = np.where(
            np.diff(session.bt_is_in_explore.astype(int)) == -1)[0] + 1
        if session.bt_is_in_explore[-1]:
            stop_explores = np.append(
                stop_explores, len(session.bt_is_in_explore))

        bout_len_frames = stop_explores - start_explores

        long_enough = bout_len_frames >= MIN_EXPLORE_TIME_FRAMES
        bout_num_wells_visited = np.zeros((len(start_explores)))
        for i, (bst, ben) in enumerate(zip(start_explores, stop_explores)):
            bout_num_wells_visited[i] = len(
                getListOfVisitedWells(session.bt_nearest_wells[bst:ben], True))
            # bout_num_wells_visited[i] = len(set(session.bt_nearest_wells[bst:ben]))
        enough_wells = bout_num_wells_visited >= MIN_EXPLORE_NUM_WELLS

        keep_bout = np.logical_and(long_enough, enough_wells)
        session.bt_explore_bout_starts = start_explores[keep_bout]
        session.bt_explore_bout_ends = stop_explores[keep_bout]
        session.bt_explore_bout_lens = session.bt_explore_bout_ends - \
            session.bt_explore_bout_starts

        probe_sm_vel = scipy.ndimage.gaussian_filter1d(
            session.probe_vel_cm_s, BOUT_VEL_SM_SIGMA)
        session.probe_sm_vel = probe_sm_vel

        probe_is_explore_local = probe_sm_vel > PAUSE_MAX_SPEED_CM_S
        dil_filt = np.ones((MIN_PAUSE_TIME_FRAMES), dtype=int)
        in_pause_bout = np.logical_not(signal.convolve(
            probe_is_explore_local.astype(int), dil_filt, mode='same').astype(bool))
        # now just undo dilation to get flags
        session.probe_is_in_pause = signal.convolve(
            in_pause_bout.astype(int), dil_filt, mode='same').astype(bool)
        session.probe_is_in_explore = np.logical_not(session.probe_is_in_pause)

        assert np.sum(np.isnan(session.probe_is_in_pause)) == 0
        assert np.sum(np.isnan(session.probe_is_in_explore)) == 0
        assert np.all(np.logical_or(session.probe_is_in_pause,
                                    session.probe_is_in_explore))
        assert not np.any(np.logical_and(
            session.probe_is_in_pause, session.probe_is_in_explore))

        start_explores = np.where(
            np.diff(session.probe_is_in_explore.astype(int)) == 1)[0] + 1
        if session.probe_is_in_explore[0]:
            start_explores = np.insert(start_explores, 0, 0)

        stop_explores = np.where(
            np.diff(session.probe_is_in_explore.astype(int)) == -1)[0] + 1
        if session.probe_is_in_explore[-1]:
            stop_explores = np.append(
                stop_explores, len(session.probe_is_in_explore))

        bout_len_frames = stop_explores - start_explores

        long_enough = bout_len_frames >= MIN_EXPLORE_TIME_FRAMES
        bout_num_wells_visited = np.zeros((len(start_explores)))
        for i, (bst, ben) in enumerate(zip(start_explores, stop_explores)):
            bout_num_wells_visited[i] = len(
                getListOfVisitedWells(session.probe_nearest_wells[bst:ben], True))
        enough_wells = bout_num_wells_visited >= MIN_EXPLORE_NUM_WELLS

        keep_bout = np.logical_and(long_enough, enough_wells)
        session.probe_explore_bout_starts = start_explores[keep_bout]
        session.probe_explore_bout_ends = stop_explores[keep_bout]
        session.probe_explore_bout_lens = session.probe_explore_bout_ends - \
            session.probe_explore_bout_starts

        # add a category at each behavior time point for easy reference later:
        session.bt_bout_category = np.zeros_like(session.bt_pos_xs)
        last_stop = 0
        for bst, ben in zip(session.bt_explore_bout_starts, session.bt_explore_bout_ends):
            session.bt_bout_category[last_stop:bst] = 1
            last_stop = ben
        session.bt_bout_category[last_stop:] = 1
        for wft, wlt in zip(session.home_well_find_times, session.home_well_leave_times):
            pidx1 = np.searchsorted(session.bt_pos_ts, wft)
            pidx2 = np.searchsorted(session.bt_pos_ts, wlt)
            session.bt_bout_category[pidx1:pidx2] = 2
        for wft, wlt in zip(session.away_well_find_times, session.away_well_leave_times):
            pidx1 = np.searchsorted(session.bt_pos_ts, wft)
            pidx2 = np.searchsorted(session.bt_pos_ts, wlt)
            session.bt_bout_category[pidx1:pidx2] = 2
        session.probe_bout_category = np.zeros_like(session.probe_pos_xs)
        last_stop = 0
        for bst, ben in zip(session.probe_explore_bout_starts, session.probe_explore_bout_ends):
            session.probe_bout_category[last_stop:bst] = 1
            last_stop = ben
        session.probe_bout_category[last_stop:] = 1
        for wft, wlt in zip(session.home_well_find_times, session.home_well_leave_times):
            pidx1 = np.searchsorted(session.probe_pos_ts, wft)
            pidx2 = np.searchsorted(session.probe_pos_ts, wlt)
            session.probe_bout_category[pidx1:pidx2] = 2
        for wft, wlt in zip(session.away_well_find_times, session.away_well_leave_times):
            pidx1 = np.searchsorted(session.probe_pos_ts, wft)
            pidx2 = np.searchsorted(session.probe_pos_ts, wlt)
            session.probe_bout_category[pidx1:pidx2] = 2

        # And a similar thing, but value == 0 for rest/reward, or i when rat is in ith bout (starting at 1)
        session.bt_bout_label = np.zeros_like(session.bt_pos_xs)
        for bi, (bst, ben) in enumerate(zip(session.bt_explore_bout_starts, session.bt_explore_bout_ends)):
            session.bt_bout_label[bst:ben] = bi + 1

        session.probe_bout_label = np.zeros_like(session.probe_pos_xs)
        for bi, (bst, ben) in enumerate(zip(session.probe_explore_bout_starts, session.probe_explore_bout_ends)):
            session.probe_bout_label[bst:ben] = bi + 1

        # ======================================================================
        # TODO
        # Some perseveration measure during away trials to see if there's an effect during the actual task
        #
        # During task effect on home/away latencies?
        #
        # average latencies for H1, A1, H2, ...
        #
        # difference in effect magnitude by distance from starting location to home well?
        #
        # Where do ripples happen? Would inform whether to split by away vs home, etc in future experiments
        #   Only during rest? Can set velocity threshold in future interruptions?
        #
        # Based on speed or exploration, is there a more principled way to choose period of probe that is measured? B/c could vary by rat
        #
        # avg speed by condition ... could explain higher visits per bout everywhere on SWR trials
        #
        # latency to home well in probe, directness of path, etc maybe?
        #   probably will be nothing, but will probably also be asked for
        #
        # Any differences b/w early vs later experiments?
        #
        # ======================================================================

        # ===================================
        # Now save this session
        # ===================================
        dataob.allSessions.append(session)
        print("done with", session.name)

        # ===================================
        # extra plotting stuff
        # ===================================
        if session.date_str in INSPECT_IN_DETAIL or INSPECT_ALL:
            if INSPECT_BOUTS and len(session.away_well_find_times) > 0:
                # print("{} probe bouts, {} bt bouts".format(
                # session.probe_num_bouts, session.bt_num_bouts))
                x = session.bt_pos_ts[0:-1]
                y = bt_sm_vel
                x1 = np.array(x, copy=True)
                y1 = np.copy(y)
                x2 = np.copy(x1)
                y2 = np.copy(y1)
                x1[session.bt_is_in_explore] = np.nan
                y1[session.bt_is_in_explore] = np.nan
                x2[session.bt_is_in_pause] = np.nan
                y2[session.bt_is_in_pause] = np.nan
                plt.clf()
                plt.plot(x1, y1)
                plt.plot(x2, y2)

                for wft, wlt in zip(session.home_well_find_times, session.home_well_leave_times):
                    pidx1 = np.searchsorted(x, wft)
                    pidx2 = np.searchsorted(x, wlt)
                    plt.scatter(x[pidx1], y[pidx1], c='green')
                    plt.scatter(x[pidx2], y[pidx2], c='green')

                print(len(session.away_well_find_times))
                for wft, wlt in zip(session.away_well_find_times, session.away_well_leave_times):
                    pidx1 = np.searchsorted(x, wft)
                    pidx2 = np.searchsorted(x, wlt)
                    plt.scatter(x[pidx1], y[pidx1], c='green')
                    plt.scatter(x[pidx2], y[pidx2], c='green')

                mny = np.min(bt_sm_vel)
                mxy = np.max(bt_sm_vel)
                for bst, ben in zip(session.bt_explore_bout_starts, session.bt_explore_bout_ends):
                    plt.plot([x[bst], x[bst]], [mny, mxy], 'b')
                    plt.plot([x[ben-1], x[ben-1]], [mny, mxy], 'r')
                if SAVE_DONT_SHOW:
                    plt.savefig(os.path.join(fig_output_dir, "bouts",
                                             session.name + "_bouts_over_time"), dpi=800)
                else:
                    plt.show()

                for i, (bst, ben) in enumerate(zip(session.bt_explore_bout_starts, session.bt_explore_bout_ends)):
                    plt.clf()
                    plt.plot(session.bt_pos_xs, session.bt_pos_ys)
                    plt.plot(
                        session.bt_pos_xs[bst:ben], session.bt_pos_ys[bst:ben])

                    wells_visited = getListOfVisitedWells(
                        session.bt_nearest_wells[bst:ben], True)
                    for w in wells_visited:
                        wx, wy = get_well_coordinates(
                            w, session.well_coords_map)
                        plt.scatter(wx, wy, c='red')

                    if SAVE_DONT_SHOW:
                        plt.savefig(os.path.join(fig_output_dir, "bouts",
                                                 session.name + "_bouts_" + str(i)), dpi=800)
                    else:
                        plt.show()

            if INSPECT_NANVALS:
                print("{} nan xs, {} nan ys, {} nan ts".format(sum(np.isnan(session.probe_pos_xs)),
                                                               sum(np.isnan(
                                                                   session.probe_pos_xs)),
                                                               sum(np.isnan(session.probe_pos_xs))))

                nanxs = np.argwhere(np.isnan(session.probe_pos_xs))
                nanxs = nanxs.T[0]
                num_nan_x = np.size(nanxs)
                if num_nan_x > 0:
                    print(nanxs, num_nan_x, nanxs[0])
                    for i in range(min(5, num_nan_x)):
                        ni = nanxs[i]
                        print("index {}, x=({},nan,{}), y=({},{},{}), t=({},{},{})".format(
                            ni, session.probe_pos_xs[ni -
                                                     1], session.probe_pos_xs[ni + 1],
                            session.probe_pos_ys[ni -
                                                 1], session.probe_pos_ys[ni],
                            session.probe_pos_ys[ni +
                                                 1], session.probe_pos_ts[ni - 1],
                            session.probe_pos_ts[ni], session.probe_pos_ts[ni+1]
                        ))

            if INSPECT_PROBE_BEHAVIOR_PLOT:
                plt.clf()
                plt.scatter(session.home_x, session.home_y,
                            color='green', zorder=2)
                plt.plot(session.probe_pos_xs, session.probe_pos_ys, zorder=0)
                plt.grid('on')
                plt.show()

            if INSPECT_PLOT_WELL_OCCUPANCIES:
                cmap = plt.get_cmap('Set3')
                make_colors = True
                while make_colors:
                    well_colors = np.zeros((48, 4))
                    for i in all_well_names:
                        well_colors[i-1, :] = cmap(random.uniform(0, 1))

                    make_colors = False

                    if ENFORCE_DIFFERENT_WELL_COLORS:
                        for i in all_well_names:
                            neighs = [i-8, i-1, i+8, i+1]
                            for n in neighs:
                                if n in all_well_names and np.all(well_colors[i-1, :] == well_colors[n-1, :]):
                                    make_colors = True
                                    print("gotta remake the colors!")
                                    break

                            if make_colors:
                                break

                # print(session.bt_well_entry_idxs)
                # print(session.bt_well_exit_idxs)

                plt.clf()
                for i, wi in enumerate(all_well_names):
                    color = well_colors[wi-1, :]
                    for j in range(len(session.bt_well_entry_times[i])):
                        i1 = session.bt_well_entry_idxs[i][j]
                        try:
                            i2 = session.bt_well_exit_idxs[i][j]
                            plt.plot(
                                session.bt_pos_xs[i1:i2], session.bt_pos_ys[i1:i2], color=color)
                        except:
                            print("well {} had {} entries, {} exits".format(
                                wi, len(session.bt_well_entry_idxs[i]), len(session.bt_well_exit_idxs[i])))

                plt.show()

    # save all sessions to disk
    dataob.saveToFile(os.path.join(output_dir, out_filename))
