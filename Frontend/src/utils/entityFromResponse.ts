import type { EntityResponse } from '../api/entities';
import type { Entity } from '../types/world';
import { getEntityDescription } from './entityDescription';

export function entityFromResponse(entity: EntityResponse): Entity {
  const attribute = (name: string) => entity.facts?.find(fact => fact.property_name === name)?.current_version?.value;
  const traits = attribute('traits');
  const subtype = attribute('subtype');
  return {
    id: entity.id,
    name: entity.canonical_name,
    type: entity.entity_type as Entity['type'],
    description: getEntityDescription(entity),
    subtype: typeof subtype === 'string' ? subtype : undefined,
    traits: Array.isArray(traits) ? traits.filter((value): value is string => typeof value === 'string') : [],
    alias: entity.aliases?.[0] || '',
    aliases: entity.aliases || [],
    facts: (entity.facts || []).map(fact => ({
      id: fact.id,
      text: `${fact.property_name}: ${fact.current_version?.value ?? ''}`,
      source: fact.current_version?.chapter_id || 'Manual Entry',
      type: fact.current_version?.chapter_id ? 'extracted' : 'manual',
      property_name: fact.property_name,
      value: fact.current_version?.value,
    })),
    relationships: [],
    appearances: [],
  };
}
