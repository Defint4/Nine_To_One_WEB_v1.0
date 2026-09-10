"""Les jeux servis par la plateforme : un dossier par jeu, inscrit dans `registry.py`.

Ce paquet n'importe aucun jeu à l'initialisation : les jeux importent la plateforme
(`app.rooms`), qui importe `app.games.base`, et cela doit rester sans cycle.
"""
