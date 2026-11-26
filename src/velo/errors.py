"""Les erreurs de Vélo.

Le problème : quand quelque chose rate (internet coupé, mauvais numéro de
station, config mal écrite), Python affiche par défaut un gros pavé illisible
(une « trace d'exception »). L'énoncé l'interdit.

La solution : chaque problème qu'on sait prévoir lève une VeloError avec une
phrase claire dedans. Tout en haut, cli.py attrape ces VeloError, affiche juste
la phrase, et quitte avec le code 1 (= « ça a raté »).
"""


class VeloError(Exception):
    """Un problème prévu. Son message est fait pour être lu par l'utilisateur."""


class ConfigError(VeloError):
    """Le fichier config.yaml est absent, ou un réglage dedans est faux."""


class NetworkError(VeloError):
    """Le site de V'Lille ne répond pas, ou renvoie des données inutilisables."""
