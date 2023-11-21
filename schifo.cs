if (!string.IsNullOrEmpty(descriptionFilter))
{
    documents = documents.Where(
        d => d.Description.ToLower().StartsWith(descriptionFilter.ToLower()))
    .ToList();
}
 
documents = documents.OrderByDescending(d => d.ContentType)
                     .ThenBy(d => d.Description)
                     .Skip(numPage * numRowsPage)
                     .Take(numRowsPage + 1)
                     .ToList();
