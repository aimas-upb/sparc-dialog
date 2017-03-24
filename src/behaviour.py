#! /usr/bin/env python
# -*- encoding: UTF-8 -*-

"""Example: A Simple class to Find Human with BasicAwareness"""

import qi
import argparse
import sys
import time
import almath

import topics as topic_module

FACE_MAX_ATTEMPTS = 100
topics = []
topic_ids = []

old_id = -1




class HumanTrackedEventWatcher(object):
    """ A class to react to HumanTracked and PeopleLeft events """

    def __init__(self, app):
        """
        Initialisation of qi framework and event detection.
        """
        super(HumanTrackedEventWatcher, self).__init__()
        app.start()
        session = app.session
        self.subscribers_list = []
        self.is_speech_reco_started = False


        # Get the services ALMemory, ALSpeechRecognition, ALBasicAwareness and ALMotion.
        self.memory = session.service("ALMemory")
        self.speech_reco = session.service("ALSpeechRecognition")

        self.alife = session.service("ALAutonomousLife")
        self.alife.setState("disabled")

        self.anim_player = session.service("ALAnimationPlayer")

        self.face_detect = session.service("ALFaceDetection")
        self.connect_callback("FaceDetected", self.on_face_detected)
        self.face_detect.subscribe("HumanTrackedEventWatcher")

        self.face_detect.enableTracking(True)
        
        self.motion = session.service("ALMotion")
        self.motion.setMotionConfig([["ENABLE_FOOT_CONTACT_PROTECTION", False]])

        self.tts = session.service("ALTextToSpeech")

        self.dialog = session.service("ALDialog")

        self.move_subscriber = self.memory.subscriber("moveDir")
        self.move_subscriber.signal.connect(self.onMoveCommand)

        self.feedback_subscriber = self.memory.subscriber("ALMotion/MoveFailed")
        self.feedback_subscriber.signal.connect(self.onMoveFailed)

        self.reply_handler = self.memory.subscriber("reply")
        self.reply_handler.signal.connect(self.onWhoAmI)

        self.animate_handler = self.memory.subscriber("animate")
        self.animate_handler.signal.connect(self.onAnimate)

        self.tracker = session.service("ALTracker")

        self.follow_handler = self.memory.subscriber("follow")
        self.follow_handler.signal.connect(self.onFollowMe)

        #   load topics
        topics = [topic_module.content_move]

        for topic in topics:
            tid = self.dialog.loadTopicContent(topic)
            topic_ids.append(tid) 
            self.dialog.activateTopic(tid)

        #   subscribe to the main dialog scenario
        self.dialog.subscribe('dialog_scenario')
        

        self.got_face = False
        self.got_person = False
        self.person_id = -1
        self.person_name = ""
        self.seen_faces = 0
        self.done = False
        self.score = 0
        self.said = False
        self.following = False


        self.bg_movement = session.service("ALBackgroundMovement")
        self.bg_movement.setEnabled(True)

        self.basic_awareness = session.service("ALBasicAwareness")
        self.connect_callback("ALBasicAwareness/HumanTracked",
                              self.on_human_tracked)
        self.connect_callback("ALBasicAwareness/HumanLost",
                              self.on_people_left)


    def onFollowMe(self, value):
        print("follow handler")
        if(value == "1" and self.got_person):
            print('Start following')
            self.tts.say("Sure, I will follow you")
            self.basic_awareness.setEngagementMode("FullyEngaged")
            self.tracker.setMode("Move")
            self.tracker.registerTarget("Face", 0.1)
            self.tracker.track("Face")
            self.following = True

            
        elif(value == "0" and self.got_person):
            print('Stop following')
            self.basic_awareness.setEngagementMode("SemiEngaged")
            self.following = False
            # self.tracker.setMode("Head")
            self.tracker.stopTracker()
            self.tracker.unregisterAllTargets()
            self.tts.say("Ok, I will stop following you")

    def onAnimate(self, value):
        print("bye = " + str(value))
        if(value == "1"):
            self.anim_player.run("animations/Stand/Gestures/BowShort_1")

    def onWhoAmI(self, value):
        if(len(self.person_name) > 0 and self.got_person):
            if(self.score >= 0.45):
                self.tts.say("You are " + self.person_name)
        else:
            self.tts.say("Sorry, but I do not know you")


    def onMoveCommand(self, value):
        if(self.following):
            return

        self.said = False
        print('Got move command')
        if(value == "forward"):
            self.basic_awareness.pauseAwareness()
            self.motion.moveTo(1,0,0)
            self.motion.waitUntilMoveIsFinished()
            self.basic_awareness.resumeAwareness()
        elif(value == "back"):
            self.basic_awareness.pauseAwareness()
            self.motion.moveTo(-1,0,0)
            self.motion.waitUntilMoveIsFinished()
            self.basic_awareness.resumeAwareness()
        elif(value == "left"):
            self.basic_awareness.pauseAwareness()
            self.motion.moveTo(0,1,0)
            self.motion.waitUntilMoveIsFinished()
            self.basic_awareness.resumeAwareness()
        elif(value == "right"):
            self.basic_awareness.pauseAwareness()
            self.motion.moveTo(0,-1,0)
            self.motion.waitUntilMoveIsFinished()
            self.basic_awareness.resumeAwareness()

    def onMoveFailed(self, value):
        if(self.following):
            return

        #   the reason why Pepper stopped: *safety / internal stop
        cause = value[0]
        #   0 = move not started / 1 = move started, but interrupted
        status = value[1]
        #   3D position of the obstacle in Frame_World
        obstacle_pos = value[2]

        if (status == 0 and not self.said):
            self.tts.say("Oops! I can't move, there is an obstacle in the way.")
            self.said = True
        elif (status == 1 and not self.said):
            self.tts.say("Oops! I stopped because I encountered an obstacle.")
            self.said = True



    def connect_callback(self, event_name, callback_func):
        """ connect a callback for a given event """
        subscriber = self.memory.subscriber(event_name)
        subscriber.signal.connect(callback_func)
        self.subscribers_list.append(subscriber)

    def on_human_tracked(self, value):
        if self.following:
            return
        """ callback for event HumanTracked """
        #         #   RESET
        # self.got_face = False
        # self.got_person = False
        # self.person_id = -1
        # self.person_name = ""
        # self.seen_faces = 0

        print("got HumanTracked: detected person with ID: ", str(value))
        if value >= 0:  # found a new person
            self.start_speech_reco()
            position_human = self.get_people_perception_data(value)
            [x, y, z] = position_human
            print "The tracked person with ID", value, "is at the position:", \
                "x=", x, "/ y=",  y, "/ z=", z

            self.got_person = True
            self.person_id = value

            #   first
            # if self.person_id == -1:
            #     self.person_id = value
            #     old_id = value
        # else:
        #     self.got_face = False
        #     self.got_person = False
        #     self.person_id = -1
        #     self.person_name = ""
        #     self.seen_faces = 0
        #     self.done = False


    def detectedNewPerson(self):
        if self.following:
            return

        if len(self.person_name) <= 0:
            self.tts.say("Hello. Sorry, but I do not know you")
        else:
            self.tts.say("Hello, " + self.person_name)

    def on_face_detected(self, value):
        if self.following:
            return
        """
        Callback for event FaceDetected.
        """
        if value != [] and self.got_person and not self.done :  # only speak the first time a face appears
            self.got_face = True
            self.seen_faces += 1
            print "I saw a face!" + str(self.seen_faces)
            # print("Hello")
            # First Field = TimeStamp.
            timeStamp = value[0]
            print "TimeStamp is: " + str(timeStamp)

            # Second Field = array of face_Info's.
            faceInfoArray = value[1]
            for j in range( len(faceInfoArray)-1 ):
                faceInfo = faceInfoArray[j]

                # First Field = Shape info.
                faceShapeInfo = faceInfo[0]

                # Second Field = Extra info (empty for now).
                faceExtraInfo = faceInfo[1]

                #   found match
                if len(faceExtraInfo[2]) > 0:
                    self.done = True
                    self.person_name = faceExtraInfo[2]
                    print "ID :" + str(faceExtraInfo[0])
                    print "SCORE: " + str(faceExtraInfo[1])

                    self.score = faceExtraInfo[1]

                    if(self.score >= 0.45):
                        self.tts.say("Hello, " + self.person_name)
                    elif(self.score >= 0.3 and self.score < 0.45):
                        self.tts.say("Hmmm. You look familiar")

                elif self.seen_faces >= FACE_MAX_ATTEMPTS:
                    self.done = True
                    self.tts.say("Hello. Sorry, but I do not know you")

                # print "Face Infos :  alpha %.3f - beta %.3f" % (faceShapeInfo[1], faceShapeInfo[2])
                # print "Face Infos :  width %.3f - height %.3f" % (faceShapeInfo[3], faceShapeInfo[4])
                #print "is Tracking enabled: " + str(self.face_detect.isTrackingEnabled())
        elif value != [] and self.done and self.got_person:
            faceInfoArray = value[1]

            for j in range(len(faceInfoArray) - 1):
                faceInfo = faceInfoArray[j]

                faceExtraInfo = faceInfo[1]
                
                if (len(faceExtraInfo[2]) > 0) and (faceExtraInfo[1] > self.score):
                    self.person_name = faceExtraInfo[2]
                    self.score = faceExtraInfo[1]

    def on_people_left(self, value):
        """ callback for event PeopleLeft """
        print "got PeopleLeft: lost person", str(value)
        self.stop_speech_reco()
        self.got_face = False
        self.got_person = False
        self.person_id = -1
        self.person_name = ""
        self.seen_faces = 0
        self.done = False

        if(self.following):
            self.following = False
            # self.tracker.setMode("Move")
            self.tracker.stopTracker()
            self.tracker.unregisterAllTargets()
            self.basic_awareness.setEngagementMode("FullyEngaged")



       

    def start_speech_reco(self):
        """ start ASR when someone's detected in event handler class """
        if not self.is_speech_reco_started:
            try:
                self.speech_reco.setVocabulary(["yes", "no"], False)
            except RuntimeError:
                print "ASR already started"
            self.speech_reco.subscribe("BasicAwareness_Test")
            self.is_speech_reco_started = True
            print "started ASR"

    def stop_speech_reco(self):
        """ stop ASR when someone's detected in event handler class """
        if self.is_speech_reco_started:
            self.speech_reco.unsubscribe("BasicAwareness_Test")
            self.is_speech_reco_started = False
            print "stopped ASR"

    def get_people_perception_data(self, id_person_tracked):
        memory_key = "PeoplePerception/Person/" + str(id_person_tracked) + \
                     "/PositionInWorldFrame"

       #  # memory_key_2 = "PeoplePerception/Person/" + str(id_person_tracked) + \
       #  #              "/IsFaceDetected"
       # ##print("is face detected " + str(self.memory.getData(memory_key_2)))
        return self.memory.getData(memory_key)



    def run(self):
        #start
        self.motion.wakeUp()
        self.basic_awareness.setEngagementMode("SemiEngaged")
        self.basic_awareness.startAwareness()

        #loop on, wait for events until manual interruption
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print "Interrupted by user, shutting down"
            #stop
            self.basic_awareness.stopAwareness()
            self.stop_speech_reco()
            #self.motion.rest()


            self.dialog.unsubscribe('dialog_scenario')

            for topic_id in topic_ids:
                self.dialog.deactivateTopic(topic_id)
                self.dialog.unloadTopic(topic_id)


            sys.exit(0)





# main
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
        app = qi.Application(["HumanTrackedEventWatcher", "--qi-url=" + connection_url])
    
    except RuntimeError:
        print ("Can't connect to Naoqi at ip \"" + args.ip + "\" on port " + str(args.port) +".\n"
               "Please check your script arguments. Run with -h option for help.")
        sys.exit(1)
    
    human_tracked_event_watcher = HumanTrackedEventWatcher(app)
    human_tracked_event_watcher.run()