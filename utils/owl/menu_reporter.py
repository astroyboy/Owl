
import csv
from pathlib import Path
from typing import Any


def flatten_menu_tree(
    menus: list[dict[str, Any]],
    parent_path: str = "",
) -> dict[str, str]:
    """Flatten a nested menu tree into {tree_path: permission}."""
    result: dict[str, str] = {}

    for menu in menus:
        if not isinstance(menu, dict):
            raise ValueError(f"Invalid menu item: {menu!r}")

        title = str(menu.get("title") or "").strip()
        if not title:
            raise ValueError(f"Menu item has no title: {menu!r}")

        path = f"{parent_path} / {title}" if parent_path else title

        if path in result:
            raise ValueError(f"Duplicate menu path: {path}")

        permission = menu.get("permission", "")
        result[path] = "" if permission is None else str(permission)

        children = menu.get("children") or []
        if not isinstance(children, list):
            raise ValueError(f"Invalid children for menu: {path}")

        result.update(flatten_menu_tree(children, path))

    return result


def build_overall_menu_report(
    menus_by_role: dict[str, list[dict[str, Any]]],
) -> list[dict[str, str]]:
    """Build one report with roles sorted alphabetically."""
    sorted_role_names = sorted(
        menus_by_role.keys(),
        key=str.casefold,
    )

    flattened_by_role = {
        role_name: flatten_menu_tree(menus_by_role[role_name])
        for role_name in sorted_role_names
    }

    all_paths = sorted(
        {
            path
            for tree in flattened_by_role.values()
            for path in tree
        },
        key=str.casefold,
    )

    rows: list[dict[str, str]] = []

    for path in all_paths:
        row: dict[str, str] = {"Tree path": path}

        for role_name in sorted_role_names:
            row[role_name] = flattened_by_role[role_name].get(path, "")

        rows.append(row)

    return rows


def export_overall_menu_csv(
    menus_by_role: dict[str, list[dict[str, Any]]],
    output_file: str | Path = "test_logs/overall_menu_comparison.csv",
) -> None:
    """Export one CSV with role columns sorted alphabetically."""
    rows = build_overall_menu_report(menus_by_role)

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    sorted_role_names = sorted(
        menus_by_role.keys(),
        key=str.casefold,
    )
    columns = ["Tree path", *sorted_role_names]

    with output_file.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[Owl] Overall menu report: {output_file}")