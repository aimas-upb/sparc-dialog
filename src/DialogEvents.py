#! /usr/bin/env python
# -*- encoding: UTF-8 -*-

"""Example: A Simple class to Find Human with BasicAwareness"""

import qi
from naoqi import *

import argparse
import sys
import time
import almath

from topics import content_move

FACE_MAX_ATTEMPTS = 100


class DialogEvents(object):
    """ A class to react to various interaction events """

    def __init__(self, app):
        """
        Initialisation of qi framework and event detection.
        """
        super(DialogEvents, self).__init__()

        app.start()
        session = app.session

        self.subscribers_list = []

        # inits
        self.got_face = False
        self.tracking_human = False
        self.person_id = -1
        self.person_name = ""
        self.face_detection_attempts = 0
        self.face_detection_done = False
        self.confidence = 0
        self.move_failed_handled = False
        self.following_mode = False
        self.is_speech_reco_started = False

        # connect to naoqi services

        # ALMemory
        self.memory_proxy = session.service("ALMemory")

        # ALSpeechRecognition
        self.speech_reco_proxy = session.service("ALSpeechRecognition")

        # ALAutonomousLife
        self.auto_life_proxy = session.service("ALAutonomousLife")
        self.auto_life_proxy.setState("disabled")

        # ALAnimationPlayer
        self.animation_player_proxy = session.service("ALAnimationPlayer")

        self.animate_handler = self.memory_proxy.subscriber("AnimationEvent")
        self.animate_handler.signal.connect(self.onAnimate)

        # ALFaceDetection
        self.face_detection_proxy = session.service("ALFaceDetection")
        self.face_detection_proxy.subscribe("DialogEvents")
        self.connectCallback("FaceDetected", self.onFaceDetected)
        self.face_detection_proxy.enableTracking(True)

        # ALRobotPosture
        self.robot_posture_proxy = session.service("ALRobotPosture")
        self.robot_posture_proxy.goToPosture("Stand", 0.5)

        # ALBackgroundMovement
        self.bg_movement_proxy = session.service("ALBackgroundMovement")
        self.bg_movement_proxy.setEnabled(True)

        # ALBasicAwareness
        self.basic_awareness_proxy = session.service("ALBasicAwareness")
        self.connectCallback("ALBasicAwareness/HumanTracked",
                             self.onHumanTracked)
        self.connectCallback("ALBasicAwareness/HumanLost",
                             self.onPeopleLeft)

        # ALMotion
        self.motion = session.service("ALMotion")
        self.motion.setMotionConfig([["ENABLE_FOOT_CONTACT_PROTECTION", False]])
        self.motion.stiffnessInterpolation(["Body"], 1.0, 1.0)

        self.move_subscriber = self.memory_proxy.subscriber("MoveDirectionEvent")
        self.move_subscriber.signal.connect(self.onMoveCommand)

        self.feedback_subscriber = self.memory_proxy.subscriber("ALMotion/MoveFailed")
        self.feedback_subscriber.signal.connect(self.onMoveFailed)

        self.follow_handler = self.memory_proxy.subscriber("FollowEvent")
        self.follow_handler.signal.connect(self.onFollowMe)

        # ALTextToSpeech
        self.tts = session.service("ALTextToSpeech")

        self.reply_handler = self.memory_proxy.subscriber("WhoAmIEvent")
        self.reply_handler.signal.connect(self.onWhoAmI)

        # ALDialog
        self.dialog = session.service("ALDialog")

        # ALTracker
        self.tracker = session.service("ALTracker")

        #   load topics
        self.topic_ids = []
        self.topics = [content_move]

        for topic in self.topics:
            tid = self.dialog.loadTopicContent(topic)
            self.topic_ids.append(tid)
            self.dialog.activateTopic(tid)

        # subscribe to the main dialog scenario
        self.dialog.subscribe('dialog_scenario')

    """
    Utils
    """

    # connect a callback to a given event
    def connectCallback(self, event_name, callback_func):
        subscriber = self.memory_proxy.subscriber(event_name)
        subscriber.signal.connect(callback_func)
        self.subscribers_list.append(subscriber)

    # TODO: why is it useful?
    # start ASR when someone's detected in event hanumanTrackedEventWatcherdler class
    def startSpeechRecognition(self):
        if not self.is_speech_reco_started:
            try:
                self.speech_reco_proxy.setVocabulary(["yes", "no"], False)
            except RuntimeError:
                print "[INFO] ASR already started"
            self.speech_reco_proxy.subscribe("BasicAwareness_Test")
            self.is_speech_reco_started = True
            print "[INFO] started ASR"

    # TODO: why is it useful?
    # stop ASR when someone's detected in event handler class
    def stopSpeechRecognition(self):
        if self.is_speech_reco_started:
            self.speech_reco_proxy.unsubscribe("BasicAwareness_Test")
            self.is_speech_reco_started = False
            print "[INFO] stopped ASR"

    # get info about a given person
    def getPeoplePerceptionData(self, id_person_tracked):
        memory_key = "PeoplePerception/Person/" + str(id_person_tracked) + \
                     "/PositionInWorldFrame"

        #  # memory_key_2 = "PeoplePerception/Person/" + str(id_person_tracked) + \
        #  #              "/IsFaceDetected"
        # ##print("is face detected " + str(self.memory.getData(memory_key_2)))
        return self.memory_proxy.getData(memory_key)

    # resets various flags and counters
    def reset(self):
        self.person_id = -1
        self.tracking_human = False
        self.person_name = ""

        self.got_face = False
        self.face_detection_done = False
        self.face_detection_attempts = 0

        # TODO: why?
        self.stopSpeechRecognition()

        if self.following_mode:
            self.following_mode = False
            self.tracker.stopTracker()
            self.tracker.unregisterAllTargets()
            self.basic_awareness_proxy.setEngagementMode("SemiEngaged")

    """
    Event handlers
    """

    def onAnimate(self, value):

        print("[INFO] [Handler] on animate")

        # run "bowing" animation
        if value == "1":
            self.animation_player_proxy.run("animations/Stand/Gestures/BowShort_1")

    def onWhoAmI(self, value):

        print("[INFO] [Handler] on who am I")

        if len(self.person_name) > 0 and self.tracking_human:
            print("[Who Am I] " + str(self.confidence))
            if self.confidence >= 0.45:
                self.tts.say("You are " + self.person_name)
        else:
            self.tts.say("Sorry, but I do not know you")

    def onMoveCommand(self, value):
        if self.following_mode:
            print("[INFO] [Handler] IGNORING on move command because <following> mode")
            return

        print("[INFO] [Handler] on move command")

        self.move_failed_handled = False

        if value == "forward":
            self.tts.say("Moving forward")
            self.basic_awareness_proxy.pauseAwareness()
            self.motion.moveTo(1, 0, 0)
            self.motion.waitUntilMoveIsFinished()
            self.basic_awareness_proxy.resumeAwareness()
        elif value == "back":
            self.tts.say("Moving backward")
            self.basic_awareness_proxy.pauseAwareness()
            self.motion.moveTo(-1, 0, 0)
            self.motion.waitUntilMoveIsFinished()
            self.basic_awareness_proxy.resumeAwareness()
        elif value == "left":
            self.tts.say("Sure, I will move left")
            self.basic_awareness_proxy.pauseAwareness()
            self.motion.moveTo(0, 1, 0)
            self.motion.waitUntilMoveIsFinished()
            self.basic_awareness_proxy.resumeAwareness()
        elif value == "right":
            self.tts.say("Sure, I will move right")
            self.basic_awareness_proxy.pauseAwareness()
            self.motion.moveTo(0, -1, 0)
            self.motion.waitUntilMoveIsFinished()
            self.basic_awareness_proxy.resumeAwareness()
        

    def onMoveFailed(self, value):
        if self.following_mode:
            print("[INFO] [Handler] IGNORING on move failed because <following> mode")
            return

        print("[INFO] [Handler] on move failed")

        # the reason why Pepper stopped: *safety / internal stop
        cause = value[0]
        #   0 = move not started / 1 = move started, but interrupted
        status = value[1]
        #   3D position of the obstacle in Frame_World
        obstacle_pos = value[2]

        if status == 0 and not self.move_failed_handled:
            self.tts.say("Oops! I can't move, there is an obstacle in the way.")
            self.move_failed_handled = True

        elif status == 1 and not self.move_failed_handled:
            self.tts.say("Oops! I stopped because I encountered an obstacle.")
            self.move_failed_handled = True

    def onFollowMe(self, value):

        print("[INFO] [Handler] on follow me")

        if value == "1" and self.tracking_human:
            print("[INFO] Start follow")

            self.tts.say("Sure, I will follow you")

            self.basic_awareness_proxy.setEngagementMode("FullyEngaged")
            self.tracker.setMode("Move")
            self.tracker.registerTarget("Face", 0.1)
            self.tracker.track("Face")

            self.following_mode = True

        elif value == "0" and self.tracking_human:
            print("[INFO] Stop follow")

            self.tts.say("Ok, I will stop following you")

            self.basic_awareness_proxy.setEngagementMode("SemiEngaged")
            self.tracker.stopTracker()
            self.tracker.unregisterAllTargets()

            self.following_mode = False

    def onHumanTracked(self, value):
        if self.following_mode:
            print("[INFO] [Handler] on human tracked: ignoring because of <following> mode")
            return

        # found a new person
        if value >= 0:
            print("[INFO] [Handler] on human tracked: detected person with ID: " + str(value))
            
            self.startSpeechRecognition()

            self.tracking_human = True
            self.person_id = value

            position_human = self.getPeoplePerceptionData(value)
            [x, y, z] = position_human

            print("\tperson ID" + str(value) + "is at the position:", \
                "x=", x, "/ y=", y, "/ z=", z)

    def onFaceDetected(self, value):
        if self.following_mode:
            print("[INFO] [Handler] on face detected: ignoring because of <following> mode")
            return

        if not self.tracking_human:
            #print("[INFO] [Handler] on face detected: ignoring because no human tracked")
            return            


        # only speak the first time a face appears
        if value != [] and not self.face_detection_done:
            print("[INFO] [Handler] on face detected")

            self.got_face = True
            self.face_detection_attempts += 1

            timestamp = value[0]

            print "\t[on face detected] face detected, attempt = " + str(self.face_detection_attempts)
            print "\t[on face detected] timestamp = " + str(timestamp)

            # Second Field = array of face_Info's.
            faceInfoArray = value[1]
            for j in range(len(faceInfoArray) - 1):
                faceInfo = faceInfoArray[j]

                # First Field = Shape info.
                faceShapeInfo = faceInfo[0]

                # Second Field = Extra info (empty for now).
                faceExtraInfo = faceInfo[1]

                #   found match
                if len(faceExtraInfo[2]) > 0:
                    self.face_detection_done = True
                    self.person_name = faceExtraInfo[2]

                    print "\t[on face detected] person ID: " + str(faceExtraInfo[0])
                    print "\t[on face detected] confidence: " + str(faceExtraInfo[1])

                    self.confidence = faceExtraInfo[1]

                    if self.confidence >= 0.45:
                        self.tts.say("Hello, " + self.person_name)

                    # elif 0.3 <= self.confidence < 0.45:
                    #     self.tts.say("Hmmm. You look familiar")

                elif self.face_detection_attempts >= FACE_MAX_ATTEMPTS:
                    self.face_detection_done = True
                    self.tts.say("Sorry, but I do not know you")

        # why?
        elif value != [] and self.face_detection_done:
            faceInfoArray = value[1]

            for j in range(len(faceInfoArray) - 1):
                faceInfo = faceInfoArray[j]

                faceExtraInfo = faceInfo[1]

                if (len(faceExtraInfo[2]) > 0) and (faceExtraInfo[1] > self.confidence):
                    self.person_name = faceExtraInfo[2]
                    self.confidence = faceExtraInfo[1]

    def onPeopleLeft(self, value):
        print "[INFO] [Handler] on people left: lost person ", str(value)

        # reset state
        self.reset()

    def run(self):
        # start
        self.motion.wakeUp()
        self.basic_awareness_proxy.setEngagementMode("SemiEngaged")
        self.basic_awareness_proxy.startAwareness()

        # loop on, wait for events until manual interruption
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print "Interrupted by user, shutting down..."

            self.basic_awareness_proxy.stopAwareness()
            self.stopSpeechRecognition()
            # self.motion.rest()

            self.dialog.unsubscribe('dialog_scenario')

            # deactivate and unload all dialog topics
            for self.topic_id in self.topic_ids:
                self.dialog.deactivateTopic(self.topic_id)
                self.dialog.unloadTopic(self.topic_id)

            sys.exit(0)


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument("--ip", type=str, default="127.0.0.1",
                        help="Robot IP address. On robot or Local Naoqi: use '127.0.0.1'.")

    parser.add_argument("--port", type=int, default=9559,
                        help="Naoqi port number")

    args = parser.parse_args()

    try:
        # Initialize qi framework.
        connection_url = "tcp://" + args.ip + ":" + str(args.port)
        app = qi.Application(["DialogEvents", "--qi-url=" + connection_url])

    except RuntimeError:
        print ("Can't connect to Naoqi at ip \"" + args.ip + "\" on port " + str(args.port) + ".\n" +
               "Please check your script arguments. Run with -h option for help.")

        sys.exit(1)

    # construct a new scenario and run it
    scenario = DialogEvents(app)
    scenario.run()
