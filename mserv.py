'''
Created on Apr 1, 2014

@author: Dario Bonino <dario.bonino@polito.it>
'''

import cherrypy
import json
import os
from subprocess import Popen, PIPE
from functools import wraps
from mutagen import mp3, flac


def jsonify(func):
    '''JSON decorator for CherryPy'''
    @wraps(func)
    def wrapper(*args, **kwargs):  # *args are the function positional arguments, kwargs are the function keyword arguments
        # call the function and store the result in the value variable
        value = func(*args, **kwargs)
        # set the response content-type to json
        cherrypy.response.headers["Content-Type"] = "application/json"
        # serialize as json
        return json.dumps(value, indent=4, default=lambda o: o.__dict__)

    return wrapper



class Track:
    '''
    A class representing a music track
    '''
    def __init__(self, filename=None):
        # the track id
        self.id = None
        
        #the file to which the track points
        self.filename = filename
        
        #extract the track description from file tags
        self.data = self.extract_metadata() 
        
    
    def extract_metadata(self):
        
        track_data = {}
        
        # default name
        track_data['title'] = self.filename[:self.filename.rfind('.')]
        track_data['album'] = None
        track_data['genre'] = None
        track_data['artist'] = None
        
        #detect the current file type
        file_type = self.filename[self.filename.rfind('.'):]
        
        # handle FLAC files
        if file_type == ".flac":
            metadata = flac.FLAC(self.filename)
            # print metadata
            try:
                track_data['title'] = metadata['title'][0]
                track_data['album'] = metadata['album'][0]
                track_data['genre'] = metadata['genre'][0]
                track_data['artist'] = metadata['artist'][0]
            except:
                pass
        #handle MP3 files
        if file_type == ".mp3":
            metadata = mp3.MP3(self.filename)
            # print metadata
            try:
                if(metadata.has_key('TIT2')):
                    track_data['title'] = metadata['TIT2'].text[0]
                if(metadata.has_key('TALB')):
                    track_data['album'] = metadata['TALB'].text[0]
                if(metadata.has_key('TCON')):
                    track_data['genre'] = metadata['TCON'].text[0]
                if(metadata.has_key('TPE2')):
                    track_data['artist'] = metadata['TPE2'].text[0]
            except:
                pass
        
        return track_data

class Tracks:
    '''
    A class for representing set of music tracks
    ''' 
    exposed = True
    
    def __init__(self, location=None):
        self.tracks = []
        #load tracks from a given directory tree
        self.scan(location)


    @jsonify
    def GET(self, resource_id=None):
        '''
        Returns the set of tracks managed by the player or the details on a single track
        '''
        if(resource_id == None):
            return {'tracks':self.tracks}
        else:
            return self.tracks[int(resource_id)];
        
    def scan(self, music_location):
        '''Walks the given directory to find mp3 and flac music files'''
        i = 0
        for directory in os.walk(music_location, followlinks=True):            
            for filename in directory[2]:
                # check the file extension
                if filename.endswith('.mp3') or filename.endswith('.flac'):
                    #set the track filename
                    current_track = Track(os.path.join(directory[0], filename))
                    #set the track id
                    current_track.id = i
                    #append the current track
                    self.tracks.append(current_track)
                    i+=1
    
class TrackFilter:
    '''
    A class for filtering tracks on the basis of track metadata, i.e., genre, artist, album
    '''
    exposed = True
    
    def __init__(self, tracks=None):
        self.tracks = tracks
    
    @jsonify
    def GET(self, filter_on = None, value = None):
        tracks = []
        if (filter_on != None) and (value != None):
            #iterate over all available tracks
            for track in self.tracks.tracks:
                #apply filter
                if (track.data[filter_on] != None) and ((track.data[filter_on].lower() == value.lower()) or (track.data[filter_on].lower().find(value.lower()) > -1)):  
                    #if the filter matches, add the track
                    tracks.append(track)
        return {"tracks":tracks}          
    
class Player:
    '''
    A class wrapping the MPlayer process and providing a rest interface to it, exploiting its slave-mode
    '''
    exposed = True
    
    def __init__(self, tracks=None):
        # the tracks database
        self.tracks = tracks
        # the current queue
        self.queue = []
        # the currently played track
        self.current = ""
        #the current status
        self.status = "stopped"
        #start the player in idle mode
        self.player = Popen("mplayer -slave -quiet -nolirc -msglevel all=-1 -idle", stdin=PIPE, stdout=PIPE, shell=True)
    
    def exit(self):
        #cleanly stop the player
        self.player.stdin.write("quit\n")
    
    @jsonify
    def PUT(self, command = None):
        '''
        handles player operations: play, stop, next
        '''
        #the player status
        status = {}
        
        #check commands
        if(command != None):
            
            #PLAY
            if command.lower() == 'play':
                #get the request body
                play_request = json.loads(cherrypy.request.body.read())
                
                #check direct track if any
                if "track" in play_request:
                    #get the track id
                    track_id=play_request["track"]
                    #debug
                    print "loadfile \"%s\"\n"%self.tracks.tracks[int(track_id)].filename
                    #change the currently playing file
                    self.player.stdin.write("loadfile \"%s\"\n"%self.tracks.tracks[int(track_id)].filename)
                    #set the current status at playing
                    self.status = "playing"
                    #set the currently played track
                    self.current = self.tracks.tracks[int(track_id)].data
                    #reset the queue
                    self.queue = []
                    #return the current status
                    status =  {"status":self.status,"current" : self.current}
                    
                #check playlist if any
                elif "playlist" in play_request:
                    #no multiple playlist supported...just play it
                    
                    #get the playlist
                    playlist = play_request["playlist"];
                   
                    #check for tracks
                    if playlist["tracks"]!= None:
                        #reset the queue
                        self.queue = []
                        #initialize the track counter
                        i = 0;
                        #for all tracks
                        for track in playlist["tracks"]:
                            #start playing the first track
                            if(i == 0):
                                self.player.stdin.write("loadfile \"%s\"\n"%self.tracks.tracks[int(track)].filename)
                                #update the inner status
                                self.status = "playing"
                                self.current = self.tracks.tracks[int(track)].data
                            else:
                                #enqueue
                                self.player.stdin.write("loadfile \"%s\" %s\n"%(self.tracks.tracks[int(track)].filename,i))
                                self.queue.append(self.tracks.tracks[int(track)].data)
                            i+=1
                        
                        #update the json status
                        status =  {"status":self.status,"current" : self.current,"queue":self.queue}   
            #STOP  
            elif command.lower() == 'stop':
                #stop playing
                self.player.stdin.write("stop\n")
                
                #update the inner status
                self.status = "stopped"
                
                #updated the jsn status
                status =  {"status":self.status}
            #NEXT
            elif command.lower() == 'next':
                #skip to next track
                self.player.stdin.write("pt_step 1\n")
                
                #update the inner status
                self.status = "playing"
                
                #handle queue composition
                if(len(self.queue) > 0):
                    #update the current track
                    self.current = self.queue[0]
                    #update the queue
                    if len(self.queue) > 1:
                        self.queue = self.queue[1:]
                    else:
                        self.queue = []
                #update the json status
                status =  {"status":self.status,"current" : self.current,"queue":self.queue}
        return status
    
    @jsonify
    def GET(self):
        return {"status":self.status,"current" : self.current,"queue":self.queue}
    
if __name__ == '__main__':
    
    allTracks = Tracks('/dati/Music/')
    trackFilter = TrackFilter(allTracks)
    player = Player(allTracks)
    
    # publish the resource at api/v1/tracks
    cherrypy.tree.mount(
    allTracks, '/api/v1/tracks',
    {'/':
        {'request.dispatch': cherrypy.dispatch.MethodDispatcher()}
    }
    )
    
    # publish the resource at api/v1/tracks/filter
    cherrypy.tree.mount(
    trackFilter, '/api/v1/tracks/filter',
    {'/':
        {'request.dispatch': cherrypy.dispatch.MethodDispatcher()}
    }
    )
    
    # publish the resource at api/v1/player
    cherrypy.tree.mount(
    player, '/api/v1/player',
    {'/':
        {'request.dispatch': cherrypy.dispatch.MethodDispatcher()}
    }
    )
    
    # activate signal listening
    if hasattr(cherrypy.engine, 'signal_handler'):
        cherrypy.engine.signal_handler.subscribe()
    #subscribe to the stop signal
    cherrypy.engine.subscribe('stop',player.exit)
    
    #start serving pages
    cherrypy.engine.start()
    cherrypy.engine.block()
        
