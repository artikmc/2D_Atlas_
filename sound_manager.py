# sound_manager.py
import pygame

class SoundManager:
    def __init__(self):
        pygame.mixer.init()
        self.music_playing = False
        
    def toggle_music(self):
        if not self.music_playing:
            pygame.mixer.music.load("background_music.mp3")
            pygame.mixer.music.play(loops=-1)  # Зацикливание
            self.music_playing = True
        else:
            pygame.mixer.music.stop()
            self.music_playing = False
