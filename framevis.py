#
#  Project     FrameVis - Video Frame Visualizer Script
#  @author     David Madison
#  @link       github.com/dmadison/FrameVis
#  @license    MIT - Copyright (c) 2019 David Madison
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import cv2
import numpy as np
import argparse
from enum import Enum, auto


class FrameVis:
	"""
	Reads a video file and outputs an image comprised of n resized frames, spread evenly throughout the file.
	"""

	default_frame_height = None  # auto, or in pixels
	default_frame_width = None  # auto, or in pixels
	default_concat_size = 1  # size of concatenated frame if automatically calculated, in pixels
	default_direction = "horizontal"  # left to right

	def visualize(self, source, nframes, height=default_frame_height, width=default_frame_width, \
		direction=default_direction, trim=False, quiet=True):
		"""
		Reads a video file and outputs an image comprised of n resized frames, spread evenly throughout the file.

		Parameters:
			source (str): filepath to source video file
			nframes (int): number of frames to process from the video
			height (int): height of each frame, in pixels
			width (int): width of each frame, in pixels
			direction (str): direction to concatenate frames ("horizontal" or "vertical")
			quiet (bool): suppress console messages

		Returns:
			visualization image as numpy array
		"""

		video = cv2.VideoCapture(source)  # open video file
		if not video.isOpened():
			raise FileNotFoundError("Source Video Not Found")
		
		# calculate keyframe interval
		video_total_frames = video.get(cv2.CAP_PROP_FRAME_COUNT)  # retrieve total frame count from metadata
		if not isinstance(nframes, int) or nframes < 1:
			raise ValueError("Number of frames must be a positive integer")
		elif nframes > video_total_frames:
			raise ValueError("Requested frame count larger than total available ({})".format(video_total_frames))
		keyframe_interval = video_total_frames / nframes  # calculate number of frames between captures

		# grab frame for dimension calculations
		success,image = video.read()  # get first frame
		if not success:
			raise IOError("Cannot read from video file")

		# calculate letterbox / pillarbox trimming, if specified
		matte_type = 0
		if trim == True:
			if not quiet:
				print("Trimming enabled, checking matting... ", end="", flush=True)

			cropping_bounds = MatteTrimmer.determine_video_bounds(source, 20)  # 20 frame samples

			crop_width = cropping_bounds[1][0] - cropping_bounds[0][0] + 1
			crop_height = cropping_bounds[1][1] - cropping_bounds[0][1] + 1

			if crop_height != image.shape[0]:  # letterboxing
				matte_type += 1
			if crop_width != image.shape[1]:  # pillarboxing
				matte_type +=2
			
			if not quiet:
				if matte_type == 0:
					print("no matting detected")
				elif matte_type == 1:
					print("letterboxing detected, cropping {} px from the top and bottom".format(int((image.shape[0] - crop_height) / 2)))
				elif matte_type == 2:
					print("pillarboxing detected, trimming {} px from the sides".format(int((image.shape[1] - crop_width) / 2)))
				elif matte_type == 3:
					print("multiple matting detected - cropping ({}, {}) to ({}, {})".format(image.shape[1], image.shape[0], crop_width, crop_height))

		# calculate height
		if height is None:  # auto-calculate
			if direction == "horizontal":  # non-concat, use video size
				if matte_type & 1 == 1:  # letterboxing present
					height = crop_height
				else:
					height = image.shape[0]  # save frame height
			else:  # concat, use default value
				height = FrameVis.default_concat_size
		elif not isinstance(height, int) or height < 1:
			raise ValueError("Frame height must be a positive integer")
		
		# calculate width
		if width is None:  # auto-calculate
			if direction == "vertical":  # non-concat, use video size
				if matte_type & 2 == 2:  # pillarboxing present
					width = crop_width
				else:
					width = image.shape[1]  # save frame width
			else:  # concat, use default value
				width = FrameVis.default_concat_size
		elif not isinstance(width, int) or width < 1:
			raise ValueError("Frame width must be a positive integer")

		# assign direction function and calculate output size
		if direction == "horizontal":
			concatenate = cv2.hconcat
			output_width = width * nframes
			output_height = height
		elif direction == "vertical":
			concatenate = cv2.vconcat
			output_width = width
			output_height = height * nframes
		else:
			raise ValueError("Invalid direction specified")

		if not quiet:
			print("\nVisualizing \"{}\" - {} by {}, from {} frames".format(source, output_width, output_height, nframes))

		# set up for the frame processing loop
		next_keyframe = keyframe_interval / 2  # frame number for the next frame grab, starting evenly offset from start/end
		finished_frames = 0  # counter for number of processed frames
		output_image = None

		while True:
			if finished_frames == nframes:
				break  # done!

			video.set(cv2.CAP_PROP_POS_FRAMES, int(next_keyframe))  # move cursor to next sampled frame
			success,image = video.read()  # read the next frame

			if not success:
				raise IOError("Cannot read from video file (frame {} out of {})".format(int(next_keyframe), video_total_frames))

			if matte_type != 0:  # crop out matting, if specified and matting is present
				image = MatteTrimmer.crop_image(image, cropping_bounds)

			image = cv2.resize(image, (width, height))  # resize to output size

			# save to output image
			if output_image is None:
				output_image = image
			else:
				output_image = concatenate([output_image, image])  # concatenate horizontally from left -> right

			finished_frames += 1
			next_keyframe += keyframe_interval  # set next frame capture time, maintaining floats

			if not quiet:
				progress_bar(finished_frames / nframes)  # print progress bar to the console

		video.release()  # close video capture

		return output_image

	@staticmethod
	def nframes_from_interval(source, interval):
		"""
		Calculates the number of frames available in a video file for a given capture interval

		Parameters:
			source (str): filepath to source video file
			interval (float): capture frame every i seconds

		Returns:
			number of frames per time interval (int)
		"""
		video = cv2.VideoCapture(source)  # open video file
		if not video.isOpened():
			raise FileNotFoundError("Source Video Not Found")

		frame_count = video.get(cv2.CAP_PROP_FRAME_COUNT)  # total number of frames
		fps = video.get(cv2.CAP_PROP_FPS)  # framerate of the video
		duration = frame_count / fps  # duration of the video, in seconds

		video.release()  # close video capture

		return int(round(duration / interval))  # number of frames per interval


class MatteTrimmer:
	"""
	Functions for finding and removing black mattes around video frames
	"""

	@staticmethod
	def find_matrix_edges(matrix, threshold):
		"""
		Finds the start and end points of a 1D array above a given threshold

		Parameters:
			matrix (arr, 1.x): 1D array of data to check
			threshold (value): valid data is above this trigger level

		Returns:
			tuple with the array indices of data bounds, start and end
		"""

		if not isinstance(matrix, (list, tuple, np.ndarray)) or len(matrix.shape) != 1:
			raise ValueError("Provided matrix is not the right size (must be 1D)")

		data_start = None
		data_end = None

		for value_id, value in enumerate(matrix):
			if value > threshold:
				if data_start is None:
					data_start = value_id
				data_end = value_id

		return (data_start, data_end)

	@staticmethod
	def find_larger_bound(first, second):
		"""
		Takes two sets of diagonal rectangular boundary coordinates and determines
		the set of rectangular boundary coordinates that contains both

		Parameters:
			first  (arr, 1.2.2): pair of rectangular coordinates, in the form [(X,Y), (X,Y)]
			second (arr, 1.2.2): pair of rectangular coordinates, in the form [(X,Y), (X,Y)]

			Where for both arrays the first coordinate is in the top left-hand corner, 
			and the second coordinate is in the bottom right-hand corner.

		Returns:
			numpy coordinate matrix containing both of the provided boundaries
		"""
		left_edge  = first[0][0] if first[0][0] <= second[0][0] else second[0][0]
		right_edge = first[1][0] if first[1][0] >= second[1][0] else second[1][0]

		top_edge = first[0][1] if first[0][1] <= second[0][1] else second[0][1]
		bottom_edge = first[1][1] if first[1][1] >= second[1][1] else second[1][1]

		return np.array([[left_edge, top_edge], [right_edge, bottom_edge]])

	@staticmethod
	def determine_image_bounds(image):
		"""
		Determines if there are any hard mattes (black bars) surrounding
		an image on either the top (letterboxing) or the sides (pillarboxing)

		Parameters:
			image (arr, x.y.c): image as 3-dimensional numpy array

		Returns:
			numpy coordinate matrix with the two opposite corners of the 
			image bounds, in the form [(X,Y), (X,Y)]
		"""

		height, width, depth = image.shape

		# check for letterboxing
		horizontal_sums = np.sum(image, axis=(1,2))  # sum all color channels across all rows
		threshold = (width * 3)  # must be below every pixel having a value of 1/255 in every channel
		vertical_edges = MatteTrimmer.find_matrix_edges(horizontal_sums, threshold)

		# check for pillarboxing
		vertical_sums = np.sum(image, axis=(0,2))  # sum all color channels across all columns
		threshold = (height * 3)  # must be below every pixel having a value of 1/255 in every channel
		horizontal_edges = MatteTrimmer.find_matrix_edges(vertical_sums, threshold)

		return np.array([[horizontal_edges[0], vertical_edges[0]], [horizontal_edges[1], vertical_edges[1]]])

	@staticmethod
	def determine_video_bounds(source, nsamples):
		"""
		Determines if any matting exists in a video source

		Parameters:
			source (str): filepath to source video file
			nsamples (int): number of frames from the video to determine bounds,
				evenly spaced throughout the video

		Returns:
			numpy coordinate matrix with the two opposite corners of the 
			video bounds, in the form [(X,Y), (X,Y)]
		"""
		video = cv2.VideoCapture(source)  # open video file
		if not video.isOpened():
			raise FileNotFoundError("Source Video Not Found")

		video_total_frames = video.get(cv2.CAP_PROP_FRAME_COUNT)  # retrieve total frame count from metadata
		if not isinstance(nsamples, int) or nsamples < 1:
			raise ValueError("Number of samples must be a positive integer")
		keyframe_interval = video_total_frames / nsamples  # calculate number of frames between captures

		next_keyframe = keyframe_interval / 2  # frame number for the next frame grab, starting evenly offset from start/end
		image_bounds = None

		for frame_number in range(nsamples):
			video.set(cv2.CAP_PROP_POS_FRAMES, int(next_keyframe))  # move cursor to next sampled frame
			success,image = video.read()  # read the next frame

			if not success:
				raise IOError("Cannot read from video file")
			
			frame_bounds = MatteTrimmer.determine_image_bounds(image)
			image_bounds = frame_bounds if image_bounds is None else MatteTrimmer.find_larger_bound(image_bounds, frame_bounds)

		video.release()  # close video capture

		return image_bounds

	@staticmethod
	def crop_image(image, bounds):
		"""
		Crops a provided image by the coordinate bounds pair provided.

		Parameters:
			image (arr, x.y.c): image as 3-dimensional numpy array
			second (arr, 1.2.2): pair of rectangular coordinates, in the form [(X,Y), (X,Y)]

		Returns:
			image as 3-dimensional numpy array, cropped to the coordinate bounds
		"""
		return image[bounds[0][1]:bounds[1][1], bounds[0][0]:bounds[1][0]]


def progress_bar(percent):
	"""Prints a progress bar to the console based on the input percentage (float)."""
	term_char = '\r' if percent < 1.0 else '\n'  # rewrite the line unless finished
	bar_length = 25  # size of the progress bar, in characters
	filled_size = int(round(bar_length * percent))  # number of 'filled' characters in the bar
	progress_string = "#" * filled_size + " " * (bar_length - filled_size)  # assembled progress bar, as a string
	print("Processing:\t[{0}]\t{1:.2%}".format(progress_string, percent), end=term_char, flush=True)


def main():
	parser = argparse.ArgumentParser(add_help=False)  # removing help so I can use '-h' for height

	parser.add_argument("source", help="file path for the video file to be visualized", type=str)
	parser.add_argument("destination", help="file path output for the final image", type=str)
	parser.add_argument("-n", "--nframes", help="the number of frames in the visualization", type=int)
	parser.add_argument("-i", "--interval", help="interval between frames for the visualization", type=float)
	parser.add_argument("-h", "--height", help="the height of each frame, in pixels", type=int, default=FrameVis.default_frame_height)
	parser.add_argument("-w", "--width", help="the output width of each frame, in pixels", type=int, default=FrameVis.default_frame_width)
	parser.add_argument("-d", "--direction", help="direction to concatenate frames, horizontal or vertical", type=str, \
		choices=["horizontal", "vertical"],	default=FrameVis.default_direction)
	parser.add_argument("-t", "--trim", help="detect and trim any hard matting (letterboxing or pillarboxing)", action='store_true', default=False)
	parser.add_argument("-q", "--quiet", help="mute console outputs", action='store_true', default=False)
	parser.add_argument("--help", action="help", help="show this help message and exit")

	args = parser.parse_args()

	if args.nframes is None:
		if args.interval is not None:  # calculate nframes from interval
			args.nframes = FrameVis.nframes_from_interval(args.source, args.interval)
		else:
			parser.error("You must provide either an --(n)frames or --(i)nterval argument")

	fv = FrameVis()

	output_image = fv.visualize(args.source, args.nframes, height=args.height, width=args.width, \
		direction=args.direction, trim=args.trim, quiet=args.quiet)
	cv2.imwrite(args.destination, output_image)  # save visualization to file

	if not args.quiet:
		print("Visualization saved to {}".format(args.destination))


if __name__ == "__main__":
	main()
