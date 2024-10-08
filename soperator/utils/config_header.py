#!/usr/bin/python3

from enum import IntEnum
from argparse import ArgumentParser, Namespace


class HeaderLevel(IntEnum):
    H1 = 1
    H2 = 2
    H3 = 3

    def count_empty(self) -> int:
        return 3 - self.value


WINDOW_WIDTH = 120


def render_filled(char: str) -> str:
    return f'#{char * (WINDOW_WIDTH - 2)}#'


def render_hr() -> str:
    return render_filled('-')


def render_empty() -> str:
    return render_filled(' ')


def render_text(text: str) -> str:
    len_text: int = len(text)
    len_text_half: int = len_text // 2
    len_left_span: int = ((WINDOW_WIDTH - 2) // 2) - len_text_half

    return f'#{" " * len_left_span}{text}{" " * (WINDOW_WIDTH - 2 - len_left_span - len_text)}#'


def render_header(title: str, level: HeaderLevel) -> str:
    lines: list[str] = []

    lines.append(render_hr())
    for _ in range(level.count_empty()):
        lines.append(render_empty())
    lines.append(render_text(title))
    for _ in range(level.count_empty()):
        lines.append(render_empty())
    lines.append(render_hr())

    return '\n'.join(lines)


def main():
    parser: ArgumentParser = ArgumentParser(add_help=False)
    parser.add_argument('-h', '--level', type=int, choices=[level for level in list(HeaderLevel)], help='The level of the header')
    parser.add_argument('title', type=str, help='The title of the header')
    args: Namespace = parser.parse_args()

    print(render_header(args.title, HeaderLevel(args.level)))


if __name__ == '__main__':
    main()
