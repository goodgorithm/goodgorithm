import styles from "./EntityTags.module.css";

export function EntityTags({ entities }: { entities: string[] }) {
  if (entities.length === 0) return null;

  return (
    <ul className={styles.tags}>
      {entities.map((entity) => (
        <li key={entity} className={styles.tag}>
          {entity}
        </li>
      ))}
    </ul>
  );
}
