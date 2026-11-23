import argparse

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="velo")

    sous_commandes = parser.add_subparsers(dest="commande", required=True)

    init = sous_commandes.add_parser("init")
    init.add_argument("--force", action="store_true")

    sous_commandes.add_parser("refresh")

    sous_commandes.add_parser("status")

    sous_commandes.add_parser("station")

    sous_commandes.add_parser("favorites")

    sous_commandes.add_parser("alerts")

    sous_commandes.add_parser("dashboard")

    sous_commandes.add_parser("collect")

    sous_commandes.add_parser("history")
    
    sous_commandes.add_parser("query")

    return parser

def main() -> None:
    ticket = build_parser().parse_args()
    print(ticket)