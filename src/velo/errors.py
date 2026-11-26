"""Erreurs propres à Vélo.

Toute erreur « prévue » (réseau indisponible, identifiant inconnu, configuration
invalide...) est levée sous la forme d'une VeloError. La CLI l'attrape, affiche
son message à l'utilisateur et quitte avec un code non nul, sans trace d'exception.
"""


class VeloError(Exception):
    """Erreur prévue, à afficher telle quelle à l'utilisateur."""


class ConfigError(VeloError):
    """Le fichier config.yaml est absent ou contient une valeur invalide."""


class NetworkError(VeloError):
    """Le réseau GBFS est injoignable ou renvoie des données inutilisables."""
